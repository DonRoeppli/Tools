@echo off

C:\Users\Nico\AppData\Local\Programs\Python\Python313\python.exe -m PyInstaller --onefile --noconsole ^
--icon="icon.ico" ^
--name="KaFlood" ^
--add-data "icon.ico;." ^
"main.py"