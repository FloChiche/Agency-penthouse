# Agent Tower — proto Blender

- `renders/` : images rendues avec Cycles (GPU RTX), 1600×900.
- `agent_tower.blend` : la scène complète, à ouvrir dans Blender 4.2 pour se balader dedans
  (chaque étage est un objet vide `etage_N` qui contient tout son mobilier).
- `agent_tower.py` : le script qui construit toute la scène. On peut le modifier
  (couleurs, étages, voitures…) puis relancer :

```
"C:\Program Files\Blender Foundation\Blender 4.2\blender.exe" -b -P agent_tower.py -- 160 100
```

## Vraies voitures

Dépose des modèles 3D (`.glb`, `.gltf`, `.fbx` ou `.obj`) dans `modeles/voitures/`.
Le script les place dans l'ordre alphabétique sur les 8 plateaux du garage (posées au sol,
centrées, mises à l'échelle). Les plateaux restants gardent les silhouettes génériques.
Astuce : préfixe les fichiers `1-`, `2-`… pour choisir l'ordre.

Arguments : nombre de samples, % de résolution, et en option une liste de caméras
(ex. `04-etage-claude-code,05-casino`) pour ne rendre que celles-là.

## Mobilier réel

`modeles/mobilier/` contient 24 modèles Poly Haven (CC0) : chaises, fauteuils, tables basses,
plantes, lustres, lampes, vases, console de jeu, lampadaires. Le script les place automatiquement ;
si un dossier manque, il revient aux meubles modélisés. Les canapés restent modélisés (style
modulaire moderne), sauf le Chesterfield noir du casino.

Chaque étage a une plaque murale (numéro + nom + couleur de l'app) sur le mur de gauche.
