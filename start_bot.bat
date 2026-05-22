@echo off
echo Dang cai dat cac thu vien can thiet...
pip install -r requirements.txt
echo Dang cai dat trinh duyet Playwright...
playwright install chromium
cls
echo =======================================
echo     BOT SAN SALE DANG CHAY LOCAL
echo =======================================
python main.py
pause
