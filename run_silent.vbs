Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c cd /d ""C:\Users\user\Desktop\我的文件 claude\tocin53 gmail 自動整理"" && ""C:\Users\user\AppData\Local\Python\bin\python.exe"" gmail_organizer.py >> gmail_organizer.log 2>&1", 0, False
