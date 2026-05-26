@echo off

python -m PyInstaller --onefile --noconsole ^
--icon="icon.ico" ^
--name="AutoWriter" ^
--add-data "icon.ico;." ^
"main.py"