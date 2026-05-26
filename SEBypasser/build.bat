@echo off

py -m PyInstaller --onefile --noconsole ^
--icon="icon.ico" ^
--name="SEBypasser" ^
--add-data "icon.ico;." ^
"main.py"