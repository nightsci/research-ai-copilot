# GitHub 与线上版本维护

仓库已创建并完成首次推送：[nightsci/research-ai-copilot](https://github.com/nightsci/research-ai-copilot)，首次提交 `b7ff840`，分支 `main`。在线演示：https://nightsci-research-ai-copilot.streamlit.app/ ，入口 `research-ai-copilot.py`，公网保持无模型密钥模式。

只在独立部署目录操作，不重复初始化仓库或添加 origin。后续更新先测试与扫描：

```powershell
Set-Location 'C:\Users\Administrator\Desktop\VScode\research-ai-copilot'
..\.deploy-check-venv\Scripts\python.exe -m pytest -q -p no:cacheprovider
..\.deploy-check-venv\Scripts\python.exe -m scripts.audit_release
git remote get-url origin
git check-ignore .env .streamlit/secrets.toml .venv/example uploads/example.pdf artifacts/example.json
git status --short
git diff --check
git diff
```

本机验证环境位于部署目录外；新电脑按 README 创建 `.venv` 后替换解释器路径。只暂存本次明确审核的文件，确认 `git diff --cached` 中没有凭据、PDF、私人材料或日志，再创建说明实际修改的提交。

```powershell
git diff --cached --check
git diff --cached --stat
git push origin main
```

不要强制推送；远程有新提交时先检查和整合，不能覆盖。不在 remote URL 中放令牌。推送后核对 GitHub main 提交及文件内容，再检查 Streamlit Cloud 构建状态和两页面；GitHub 更新不等于云端构建成功。当前不配置模型密钥；收费演示须先完成 [受控方案](CONTROLLED_AI_DEMO.md)。

安全扫描不保证发现所有形式的密钥；若密钥曾提交到 Git，删除工作区文件不能清除历史，需要先撤销/轮换密钥，再处理历史。不要使用 `git add -f` 强制加入被忽略的文件。
