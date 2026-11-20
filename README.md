# FastAPI → Render CI/CD

[![pipeline](https://github.com/pavelsilinskiiwork/fastapi-render-cicd/actions/workflows/pipeline.yml/badge.svg?branch=main)](https://github.com/pavelsilinskiiwork/fastapi-render-cicd/actions/workflows/pipeline.yml)

A GitHub Actions pipeline that ships a FastAPI service to Render **only after every check passes**, and then
**proves the new commit is the one running in production**. The service is tiny on purpose; the pipeline is the
project.

```
pull request / push to main
        │
        ├── lint     ruff check + ruff format --check
        ├── test     pytest on Python 3.11 / 3.12 / 3.13, coverage gate (90%)
        └── docker   build the image, run the container, smoke-test it
                │
                ▼   (push to main only, all three green)
        deploy   ── environment "production"
                    1. call Render's deploy hook for this exact commit (&ref=<sha>)
                    2. poll /version until production reports that commit
                    3. check /health  → pipeline goes green only now
```

## What each gate catches

| Gate | Catches |
| --- | --- |
| `lint` | style drift, unused imports, likely bugs (ruff rules E, F, I, B, UP) |
| `test` | broken behaviour; differences between Python versions; untested code (coverage below 90% fails) |
| `docker` | a Dockerfile that does not build, or an image whose service does not start |
| `deploy` / hook | nothing deploys unless the three jobs above passed (`needs:`); only `main` deploys |
| `deploy` / smoke test | "deploy queued" is not "deploy live": the job fails if production does not report the new commit within 15 minutes or `/health` is not ok |

Other choices worth knowing about:

- **One deploy at a time.** `concurrency: deploy-production` queues deploys instead of overlapping them; a
  newer pull request run cancels the older one.
- **Least privilege.** The workflow token is `contents: read`. The deploy hook is a secret and is never printed.
- **The smoke-test script is tested** (`tests/test_smoke_script.py`) against a real local HTTP server: old version
  still answering, service unreachable during a deploy, new commit live but unhealthy, timeout.
- **Dependabot** keeps the Actions, pip packages and the base Docker image up to date.

## Set it up

1. **Create the repository** on GitHub and push this code to `main`.
2. **Create the Render service.** Either use *New → Blueprint* (reads `render.yaml`) or create a Web Service from
   this repo with the Docker runtime. In *Settings → Build & Deploy* set **Auto-Deploy to Off**: the pipeline
   decides when to deploy. Health check path: `/health`.
3. **Connect the pipeline to Render.**
   - In Render: *Settings → Deploy Hook* → copy the URL.
   - In GitHub: *Settings → Environments → New environment* named `production`.
     Add the secret `RENDER_DEPLOY_HOOK_URL` (the hook URL) and the variable `SERVICE_URL`
     (for example `https://fastapi-render-cicd.onrender.com`).
4. **Protect `main`** (*Settings → Branches*): require the `lint`, `test` and `docker` checks before merging.
5. Push a commit. Watch *Actions*: after the three checks pass, `deploy` waits for production to report the commit.

## Prove that the gates work

Do these once and keep the screenshots of the runs, they are the real evidence:

1. **Failing test.** Change an assertion in `tests/test_api.py`, push to a branch, open a pull request: `test` goes red.
   Merge is blocked; no deploy.
2. **Broken Dockerfile.** Misspell a file name in `COPY main.py .`: `docker` goes red, `deploy` is skipped.
3. **Version proof.** After a green deploy, open `https://<your-service>/version`: `commit` equals the commit
   shown in the run.

## Run it locally

```bash
pip install -r requirements-dev.txt
python -m pytest --cov=main --cov=scripts
ruff check . && ruff format --check .
uvicorn main:app --reload

docker build -t service .
docker run -p 8000:8000 -e GIT_SHA=local service
python scripts/smoke_test.py http://localhost:8000 --sha local --timeout 30 --interval 2
```

## Limitations

- On Render's free plan the service sleeps after inactivity and the first request after a deploy can take about a
  minute, which is why the smoke test waits up to 15 minutes and polls every 15 seconds.
- There is no automated rollback. Render keeps serving the previous version if the new one fails its health check;
  a deploy that goes live but misbehaves is rolled back by redeploying an earlier commit from the Render dashboard.
- Render also has a built-in option to deploy after CI checks pass. This repository uses an explicit hook plus a
  live-version check, because that makes the gate and the proof visible in the workflow itself.
- The service has no database or secrets, so there are no migrations or secret rotation steps in the pipeline.
