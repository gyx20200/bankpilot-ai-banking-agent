# BankPilot Day 1 Starter — Windows 开发机

目标：在本机运行 **Vue (5173) → FastAPI (8000) → Spring Boot (8080) → MySQL (3306)**，网页输入「查询我的余额」得到真实的本地模拟数据库数据。

> 警告：这只是第一天的本地读操作演示，**尚未接入 LLM、身份认证或转账授权**。固定 demo user=1，切勿部署到公网。所有账号均为虚构。

## 准备软件
1. Java JDK 21（如 Eclipse Temurin）
2. Apache Maven 3.9+（或使用 Spring Initializr 生成的 Maven Wrapper `mvnw.cmd`）
3. Python 3.11+
4. Node.js 24 LTS
5. MySQL 8.0 Server + Workbench
6. Git + VS Code

下载：
- https://adoptium.net/temurin/releases/?version=21
- https://maven.apache.org/download.cgi
- https://www.python.org/downloads/windows/
- https://nodejs.org/en/download
- https://dev.mysql.com/downloads/windows/installer/
- https://code.visualstudio.com/download
- https://git-scm.com/downloads/win

## A. 创建数据库（成员 A，MySQL Workbench）
1. 打开 `database/init.sql`，先将 `REPLACE_WITH_YOUR_LOCAL_PASSWORD` 改为自己设置的本地密码。
2. 在 Workbench 中连接本机 MySQL（MySQL 的 root 登录密码是安装时自己设定的），使用 `File > Open SQL Script` 打开该文件。
3. 点击闪电按钮运行。最后应显示张小明的 DEMO-6688 账户余额 12580.50，李四余额 5000.00。
4. 需要重新设置应用数据库密码时，可在 Workbench 执行 `ALTER USER 'bankpilot_app'@'localhost' IDENTIFIED BY '新的密码';`。
5. 不要把修改后的密码文件提交到 GitHub！建议先编辑一份本地临时 SQL 副本运行，保留仓库源文件中的占位符不变。

## B. Java 服务（成员 A，PowerShell）
```powershell
cd banking-backend
java -version
mvn -version
$env:DB_PASSWORD = "这里填上面设置的bankpilot_app密码"
mvn spring-boot:run
```
如果是通过 https://start.spring.io 生成的 Spring Boot Maven 项目并已复制本仓库的源码和 `application.properties`，可改用 `./mvnw.cmd spring-boot:run`，不必另装 Maven。

浏览器打开 http://127.0.0.1:8080/api/demo/balance ，看到 JSON，其中有 `12580.50` 就成功。

## C. Python 服务（成员 B，第二个 PowerShell 窗口）
```powershell
cd agent-service
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```
访问 http://127.0.0.1:8000/docs 可在 Swagger 测试 POST `/api/agent/chat`，请求体：`{"message":"查询我的余额"}`。

## D. Vue 前端（成员 B，第三个 PowerShell 窗口）
```powershell
cd frontend
npm install
npm run dev
```
浏览器打开 http://127.0.0.1:5173 ，输入「查询我的余额」并发送。

## 两台电脑联调
这份起步包默认全部通过 `127.0.0.1` 访问，即只能在同一台电脑上端到端运行。**推荐先在 A 的电脑完整跑通**，B 通过 GitHub 提交前端和 Python 代码。随后再使用 Tailscale 或局域网代理进行分机联调；不要直接把无鉴权的数据库或服务开放到互联网。

## Windows 常见问题
- PowerShell 不允许激活虚拟环境：不必改系统安全设置，直接运行 `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` 和 `.\.venv\Scripts\python.exe -m uvicorn main:app --host 127.0.0.1 --port 8000`。
- `mvn` 不存在：安装 Maven 并配置 PATH，或使用 Spring Initializr 创建 Maven Wrapper。
- Java 数据源连接失败：检查 MySQL 服务是否启动、数据库 `bankpilot` 是否创建、应用账号密码以及 MySQL 是否监听 3306。
- Maven/npm/pip 下载失败：检查本地网络，按各自官方文档设置镜像源或代理，不要随意执行未知镜像脚本。
- 8080、8000、5173 冲突：关闭占用端口的旧服务，不要随意改变端口而遗漏联动配置。
