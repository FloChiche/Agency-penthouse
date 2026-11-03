' Agent Tower en arrière-plan : lance le serveur sans fenêtre et le relance s'il s'arrête.
' Copié dans le dossier Démarrage de Windows pour tourner dès l'ouverture de session.
Set shell = CreateObject("WScript.Shell")
dir = "C:\Users\Floch\Desktop\agent-tower"
Do
  shell.Run "cmd /c cd /d """ & dir & """ && node server\server.js >> """ & dir & "\server.log"" 2>&1", 0, True
  WScript.Sleep 5000
Loop
