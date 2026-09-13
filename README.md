# Piappify
Just convert your git hub repository into android application, just paste your link and hit generate 
# Android Cloud Compiler

A production-grade, self-hosted Streamlit service that compiles public GitHub repositories containing Kivy/KivyMD/Flet Python apps into Android APKs via Buildozer.

## Architecture
This project uses a strictly isolated, ephemeral cloud build model (Model B):
- **Frontend:** Streamlit Community Cloud (handles UI, validation, and orchestration).
- **Backend:** GitHub Actions (provisions a fresh, isolated Ubuntu container with Android SDK/NDK, runs Buildozer, and destroys the container immediately after).

## Deployment Instructions

1. **Fork/Clone** this repository to your GitHub account.
2. **Update Configuration:** Open `app.py` and update `BUILDER_REPO_OWNER` and `BUILDER_REPO_NAME` to match your GitHub username and this repository's name.
3. **Deploy to Streamlit Cloud:**
   - Go to [share.streamlit.io](https://share.streamlit.io/) and sign in with GitHub.
   - Click **"New app"** and point it to this repository.
   - Set the Main file path to `app.py`.
4. **Add Secrets:**
   - In your Streamlit Cloud app dashboard, go to **Settings > Secrets**.
   - Add your GitHub Personal Access Token (requires `repo` and `workflow` scopes):
     ```toml
     GITHUB_TOKEN = "ghp_your_actual_token_here"
     ```
5. **Deploy.**
