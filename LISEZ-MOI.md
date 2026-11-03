# Agent Tower

Suivi en direct de tes IA dans une tour 3D à Manhattan (la scène Blender de `design prototypes/v3 - Blender`).

## Lancer

- `start.bat` : lance la tour et ouvre http://localhost:4317
- `demo.bat` : idem avec une activité simulée (pratique pour voir les agents bouger)
- Le bouton « Démo » du panneau *En direct* active/désactive la simulation à chaud.

Il faut Node.js (déjà installé sur ce PC). Aucune dépendance à installer.

## Accès depuis tous tes appareils (Tailscale)

- Adresse : **https://flo.tailc021f8.ts.net** (uniquement sur ton réseau Tailscale, pas sur Internet).
- Publication : `tailscale serve --bg 4317` (à refaire seulement si tu la retires avec `tailscale serve reset`).
- Toujours allumé : `tower-service.vbs` lance le serveur sans fenêtre et le relance s'il s'arrête.
  Pour qu'il démarre avec Windows, copie-le dans le dossier Démarrage (`Win + R` → `shell:startup`).
  Journal : `server.log`. Le PC doit rester allumé (pas en veille).
- Accès public (n'importe quel ordi) : `tailscale funnel --bg 4317`, retirer avec `tailscale funnel reset`.
  Tout accès qui passe par Tailscale demande le mot de passe de `config.json` (`"password"`, n'importe quel
  identifiant) ; les hooks ne sont acceptés qu'en local.

## Les étages

| Étage | Qui | Source |
|---|---|---|
| 4 | Claude Code | hooks Claude Code (précis : tâche, outil, sous-agents) |
| 3 | n8n | API n8n locale (exécutions en cours, réussites, erreurs) |
| 2 | Claude (app) | à brancher — voir « Reste à faire » |
| 1 | ChatGPT (app) | à brancher — voir « Reste à faire » |

Comportement : au travail → bureau de son étage ; vient de finir → canapé ; en pause depuis
plus de 90 s → casino ou nightclub ; hors ligne → café du lobby. Les changements d'étage passent
par l'ascenseur panoramique. Les sous-agents de Claude Code apparaissent autour de son bureau.

## Brancher Claude Code

```
node hooks\install-hooks.js
```

Ajoute les hooks dans `~/.claude/settings.json` (sauvegarde faite dans `settings.json.bak-agent-tower`).
Pour les retirer : `node hooks\install-hooks.js --remove`. Si la tour n'est pas lancée, les hooks
rendent la main immédiatement : Claude Code n'est jamais ralenti.

## Brancher n8n

Dans n8n : *Settings → n8n API → Create an API key*, puis colle la clé dans `config.json`
(`"apiKey": "..."`) et relance `start.bat`.

## Limites d'usage Claude

Lues comme le fait la commande `/usage` de Claude Code, à partir de la connexion de Claude Code
sur ce PC. Il faut donc que Claude Code en ligne de commande soit connecté (`claude` puis `/login`).
Adresse interne d'Anthropic, non documentée : elle peut changer.

## Reste à faire (à voir avec ton ami)

- ChatGPT et Claude en applications de bureau : présence (app au premier plan) ou extension navigateur.
- Limites ChatGPT : seules celles de Codex sont lisibles.

## Mettre à jour la tour 3D

La tour vient du script Blender. Après une modification de la scène :

```
set AGENT_TOWER_EXPORT=C:\Users\Floch\Desktop\agent-tower\web\assets\tower.glb
"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" -b -P "..\design prototypes\v3 - Blender\agent_tower.py"
```

## Dépôt

- `config.json` n'est pas versionné (mot de passe, clé n8n) : copie `config.example.json` en `config.json`,
  puis ajoute `"password": "..."` si la tour est accessible depuis Tailscale ou Internet.
- `design-prototypes/` : les prototypes v1, v2 et le script Blender v3. La scène `.blend`, les rendus et
  les modèles 3D (voitures, mobilier) restent en local, trop lourds pour GitHub ; leurs crédits sont inclus.
