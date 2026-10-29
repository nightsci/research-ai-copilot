# 确认后上传 GitHub

本轮未执行以下命令，未创建远程仓库。只上传独立部署目录，不能上传整个上级 VScode 文件夹。

1. 在 GitHub 创建空仓库 `research-ai-copilot`；建议先选 Private，确认无秘密与私人资料后再考虑 Public。
2. 在部署目录运行安全扫描，再初始化本地仓库：

```powershell
Set-Location 'C:\Users\Administrator\Desktop\VScode\research-ai-copilot'
.\.venv\Scripts\python.exe -m scripts.audit_release
git init -b main
git check-ignore .env .streamlit/secrets.toml .venv/example uploads/example.pdf artifacts/example.json
git add README.md requirements.txt requirements-dev.txt .python-version .gitignore .env.example research-ai-copilot.py scholar rag tests scripts docs .streamlit/config.toml .streamlit/secrets.toml.example
git status --short
git diff --cached --stat
```

3. 确认暂存文件没有 `.env`、实际 `secrets.toml`、PDF、虚拟环境、个人材料及日志，再提交。不要把包含凭据的差异输出发给他人。

```powershell
git commit -m "Prepare Research AI Copilot portfolio release"
git remote add origin https://github.com/YOUR_USERNAME/research-ai-copilot.git
git push -u origin main
```

4. 使用自己的 GitHub 用户名替换 `YOUR_USERNAME`，通过 GitHub 正常认证，不在 remote URL 中放令牌。
5. 在 Streamlit Cloud 创建应用，选择该仓库、main 分支、`research-ai-copilot.py`，Python 3.12。Secrets 在平台填写。先做无密钥验收，再决定是否启用收费模型。

安全扫描不保证发现所有形式的密钥；若密钥曾提交到 Git，删除工作区文件不能清除历史，需要先撤销/轮换密钥，再处理历史。不要使用 `git add -f` 强制加入被忽略的文件。
