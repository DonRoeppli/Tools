@echo off

py -m PyInstaller --onefile --noconsole ^
--icon="icon.ico" ^
--name="MentiFlood" ^
--add-data "icon.ico;." ^
"main.py"