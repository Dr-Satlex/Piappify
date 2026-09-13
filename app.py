import streamlit as st
import requests
import re
import uuid
import time

# --- Input Contracts (Strict Validation) ---
GITHUB_URL_REGEX = re.compile(r"^https://github\.com/([A-Za-z0-9._-]+)/([A-Za-z0-9._-]+?)(?:\.git)?/?$")
APP_NAME_REGEX = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 \-]{0,49}$")
PACKAGE_NAME_REGEX = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")

# --- Configuration ---
# IMPORTANT: Update these to match your GitHub username and repository name
BUILDER_REPO_OWNER = "YOUR_GITHUB_USERNAME" 
BUILDER_REPO_NAME = "android-cloud-compiler"

def main():
    st.set_page_config(page_title="Cloud APK Builder", layout="wide")
    st.title("☁️ Android Cloud Compiler")
    st.caption("Powered by Streamlit (UI) and GitHub Actions (Ephemeral Builder)")
    
    if "GITHUB_TOKEN" not in st.secrets:
        st.error("🔒 Missing `GITHUB_TOKEN` in Streamlit Secrets. Please add it in the Streamlit Cloud dashboard.")
        return

    token = st.secrets["GITHUB_TOKEN"]
    
    with st.form("build_form"):
        st.subheader("1. Project Details")
        github_url = st.text_input("Public GitHub Repository URL", placeholder="https://github.com/kivy/kivy")
        app_name = st.text_input("App Display Name", placeholder="My Kivy App", max_chars=50)
        package_name = st.text_input("Package Name (Reverse DNS)", placeholder="com.example.myapp", max_chars=200)
        
        submitted = st.form_submit_button("🚀 Trigger Cloud Build", disabled=st.session_state.get("build_active", False))
        
        if submitted:
            # Validate Inputs
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
            
            # Trigger GitHub Action
            url = f"https://api.github.com/repos/{BUILDER_REPO_OWNER}/{BUILDER_REPO_NAME}/actions/workflows/build_worker.yml/dispatches"
            headers = {
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28"
            }
            payload = {
                "ref": "main",
                "inputs": {
                    "repo_url": github_url,
                    "app_name": app_name,
                    "package_name": package_name,
                    "build_id": build_id
                }
            }
            
            res = requests.post(url, json=payload, headers=headers)
            if res.status_code == 204:
                st.session_state["build_active"] = True
                st.session_state["build_id"] = build_id
                st.session_state["start_time"] = time.time()
                st.rerun()
            else:
                st.error(f"Failed to trigger build: {res.text}")

    # --- Active Build Polling ---
    if st.session_state.get("build_active"):
        st.divider()
        poll_build_status(st.session_state["build_id"], token, st.session_state["start_time"])

    # --- Download UI ---
    if st.session_state.get("artifact_id"):
        st.divider()
        st.success("✅ APK Compiled Successfully!")
        
        art_id = st.session_state["artifact_id"]
        dl_url = f"https://api.github.com/repos/{BUILDER_REPO_OWNER}/{BUILDER_REPO_NAME}/actions/artifacts/{art_id}/zip"
        headers = {"Authorization": f"Bearer {token}"}
        
        with st.spinner("Fetching artifact from GitHub..."):
            dl_res = requests.get(dl_url, headers=headers)
            
        if dl_res.status_code == 200:
            st.download_button(
                label="📥 Download Compiled APK (.zip)",
                data=dl_res.content,
                file_name=f"app-{st.session_state.get('build_id', 'compiled')}.zip",
                mime="application/zip",
                type="primary"
            )
            if st.button("Clear & Build Another"):
                for key in ["build_active", "artifact_id", "build_id", "start_time"]:
                    st.session_state.pop(key, None)
                st.rerun()
        else:
            st.error("Failed to fetch artifact. It may have expired.")

@st.fragment(run_every=10)
def poll_build_status(build_id, token, start_time):
    elapsed = time.time() - start_time
    
    if elapsed > 1200: # 20 minute hard timeout
        st.session_state["build_active"] = False
        st.error("Build timed out or failed. Check your repository's 'Actions' tab for detailed logs.")
        st.rerun(scope="app")
        return
        
    st.info(f"⏳ Building `{build_id}` in isolated cloud container... ({int(elapsed//60)}m {int(elapsed%60)}s elapsed)")
    st.progress(min(elapsed / 600, 0.99)) # Visual progress up to 10 mins
    
    artifact_name = f"apk-{build_id}"
    url = f"https://api.github.com/repos/{BUILDER_REPO_OWNER}/{BUILDER_REPO_NAME}/actions/artifacts"
    headers = {"Authorization": f"Bearer {token}"}
    
    try:
        res = requests.get(url, headers=headers).json()
        for art in res.get("artifacts", []):
            if art["name"] == artifact_name and not art["expired"]:
                st.session_state["build_active"] = False
                st.session_state["artifact_id"] = art["id"]
                st.rerun(scope="app") # Break fragment and rerun app to show download button
                return
    except Exception as e:
        st.warning(f"Polling error: {e}")

if __name__ == "__main__":
    main()
