@echo off

py -m PyInstaller --onefile --noconsole ^
--icon="icon.ico" ^
--name="KaFlood" ^
--add-data "icon.ico;." ^
"main.py"
