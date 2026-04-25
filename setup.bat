@echo off
echo ================================================
echo  ULTRON ASSISTANT - Setup Automatico
echo ================================================
echo.

:: Verifica Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRO] Python nao encontrado. Instale Python 3.11+ em python.org
    pause
    exit /b 1
)

echo [1/4] Criando ambiente virtual...
python -m venv venv
call venv\Scripts\activate.bat

echo [2/4] Instalando dependencias...
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet

echo [3/4] Instalando browsers do Playwright...
python -m playwright install chromium

echo [4/4] Configurando arquivo .env...
if not exist .env (
    copy .env.example .env
    echo.
    echo [ATENCAO] Arquivo .env criado. Edite-o e preencha suas chaves de API antes de executar.
) else (
    echo .env ja existe. Pulando.
)

echo.
echo ================================================
echo  Setup concluido!
echo  Proximos passos:
echo  1. Edite o arquivo .env com suas chaves de API
echo  2. Edite contacts.json com seus contatos
echo  3. Execute: venv\Scripts\activate ^&^& python main.py
echo ================================================
pause
