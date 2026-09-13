import streamlit as st
import requests
import re
import uuid
import time
import calendar
import io
import zipfile

# --- Input Contracts (Strict Validation) ---
GITHUB_URL_REGEX = re.compile(r"^https://github\.com/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")
APP_NAME_REGEX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 \-]{0,49}$")
PACKAGE_NAME_REGEX = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

# --- Configuration ---
BUILDER_REPO_OWNER = "Dr-Satlex"
BUILDER_REPO_NAME = "Piappify"
WORKFLOW_FILE = "build_worker.yml"
WORKFLOW_TIMEOUT_MIN = 25   # MUST match timeout-minutes in build_worker.yml
UI_GRACE_SECONDS = 120

API = f"https://api.github.com/repos/{BUILDER_REPO_OWNER}/{BUILDER_REPO_NAME}"


def _headers(token):
    return {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }


def gh(token, path, **kw):
    return requests.get(f"{API}{path}", headers=_headers(token), **kw)


def _extract_apk(zip_bytes, build_id):
    """Serve the raw .apk, not the artifact zip (review item #1)."""
    try:
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
            names = [n for n in z.namelist() if n.lower().endswith(".apk")]
            if names:
                return f"{build_id}-{names[0].split('/')[-1]}", z.read(names[0])
    except zipfile.BadZipFile:
        pass
    return f"app-{build_id}.zip", zip_bytes


def main():
    st.set_page_config(page_title="Cloud APK Builder", layout="wide")
    st.title("☁️ Android Cloud Compiler")
    st.caption("Streamlit orchestrates; an ephemeral GitHub Actions runner compiles.")

    if "GITHUB_TOKEN" not in st.secrets:
        st.error("🔒 Missing `GITHUB_TOKEN` in Streamlit Secrets.")
        return
    token = st.secrets["GITHUB_TOKEN"]

    with st.form("build_form"):
        st.subheader("1. Project Details")
        github_url = st.text_input("Public GitHub Repository URL", placeholder="https://github.com/owner/repo")
        app_name = st.text_input("App Display Name", placeholder="My Kivy App", max_chars=50)
        package_name = st.text_input("Package Name (Reverse DNS)", placeholder="com.example.myapp", max_chars=200)

        submitted = st.form_submit_button("🚀 Trigger Cloud Build",
                                            disabled=st.session_state.get("build_active", False))
        if submitted:
            if not GITHUB_URL_REGEX.match(github_url or ""):
                st.error("Invalid GitHub URL. Must be exact format: https://github.com/owner/repo")
                return
            if not APP_NAME_REGEX.match(app_name or ""):
                st.error("Invalid App Name. Letters, digits, spaces, hyphens only (1-50 chars).")
                return
            if not PACKAGE_NAME_REGEX.match(package_name or ""):
                st.error("Invalid Package Name. Must be lowercase reverse-DNS with at least 2 segments.")
                return

            build_id = uuid.uuid4().hex[:8]
            res = requests.post(
                f"{API}/actions/workflows/{WORKFLOW_FILE}/dispatches",
                json={"ref": "main",
                      "inputs": {"repo_url": github_url, "app_name": app_name,
                                 "package_name": package_name, "build_id": build_id}},
                headers=_headers(token),
            )
            if res.status_code == 204:
                st.session_state.update(build_active=True, build_id=build_id,
                                        dispatch_time=time.time(), run_id=None,
                                        artifact_id=None, build_failed=None)
                st.rerun()
            else:
                st.error(f"Failed to trigger build: {res.text}")

    if st.session_state.get("build_active"):
        st.divider()
        poll_build(token)

    if st.session_state.get("build_failed"):
        st.divider()
        st.error(f"❌ Build ended with status: {st.session_state['build_failed']}. "
                 "Open Piappify → Actions → latest run for the full log.")
        if st.button("Clear & Try Another Repo"):
            for k in ("build_active", "artifact_id", "build_id", "dispatch_time", "run_id", "build_failed"):
                st.session_state.pop(k, None)
            st.rerun()

    if st.session_state.get("artifact_id"):
        st.divider()
        st.success("✅ APK compiled successfully!")
        art_id = st.session_state["artifact_id"]
        with st.spinner("Fetching artifact…"):
            dl = requests.get(f"{API}/actions/artifacts/{art_id}/zip", headers=_headers(token))
        if dl.status_code == 200:
            apk_name, apk_bytes = _extract_apk(dl.content, st.session_state.get("build_id", "app"))
            st.download_button("📥 Download APK", data=apk_bytes, file_name=apk_name,
                               mime="application/vnd.android.package-archive", type="primary")
            if st.button("Clear & Build Another"):
                for k in ("build_active", "artifact_id", "build_id", "dispatch_time", "run_id", "build_failed"):
                    st.session_state.pop(k, None)
                st.rerun()
        else:
            st.error("Failed to fetch artifact. It may have expired.")


@st.fragment(run_every=10)
def poll_build(token):
    ss = st.session_state
    elapsed = time.time() - ss["dispatch_time"]
    limit = WORKFLOW_TIMEOUT_MIN * 60 + UI_GRACE_SECONDS

    if elapsed > limit:
        ss["build_active"] = False
        ss["build_failed"] = "timeout"
        st.rerun(scope="app")
        return

    st.info(f"⏳ Build `{ss['build_id']}` running in ephemeral container… "
            f"({int(elapsed//60)}m {int(elapsed%60)}s elapsed)")
    st.progress(min(elapsed / (WORKFLOW_TIMEOUT_MIN * 60), 0.99))

    # Bind dispatch -> exact run ID (review item #5)
    if not ss.get("run_id"):
        runs = gh(token, "/actions/runs", params={"per_page": 5}).json()
        for run in runs.get("workflow_runs", []):
            created = calendar.timegm(time.strptime(run["created_at"], "%Y-%m-%dT%H:%M:%SZ"))
            if created >= ss["dispatch_time"] - 30 and run.get("name") == "APK Builder Worker":
                ss["run_id"] = run["id"]
                break
        if not ss.get("run_id"):
            st.caption("Waiting for a runner to pick up the job…")
            return

    run = gh(token, f"/actions/runs/{ss['run_id']}").json()
    st.caption(f"Workflow run #{run.get('run_number')} — status: {run.get('status')}")

    # Live log tail (review item #10)
    jobs = gh(token, f"/actions/runs/{ss['run_id']}/jobs").json().get("jobs", [])
    if jobs:
        try:
            logs = requests.get(jobs[0]["url"] + "/logs", headers=_headers(token))
            if logs.status_code == 200:
                tail = "\n".join(logs.text.splitlines()[-40:])
                with st.expander("📜 Live build log (last 40 lines)"):
                    st.code(tail, language="text")
        except Exception:
            pass

    if run.get("status") == "completed":
        if run.get("conclusion") == "success":
            arts = gh(token, f"/actions/runs/{ss['run_id']}/artifacts").json().get("artifacts", [])
            target = next((a for a in arts if a["name"] == f"apk-{ss['build_id']}"), None)
            if target:
                ss["build_active"] = False
                ss["artifact_id"] = target["id"]
                st.rerun(scope="app")
                return
        ss["build_active"] = False
        ss["build_failed"] = run.get("conclusion") or "failure"
        st.rerun(scope="app")


if __name__ == "__main__":
    main()
