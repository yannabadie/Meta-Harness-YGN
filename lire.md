# Audit vivant du repo

Date de mise a jour: 2026-04-08
Branche de travail: `codex`

## Verdict actuel

Le diagnostic de fond du premier audit etait bon: le repo avait de vraies bonnes idees, mais un ecart trop large entre le recit, la robustesse runtime et la preuve QA.

Depuis, une partie importante des critiques initiales a ete corrigee. Le repo reste plus fort comme socle technique que comme produit industrialise, mais il est nettement plus coherent qu'au moment du premier texte.

## Corrige depuis le premier audit

### 1. Storage / config / frontier unifies

- `scripts/config.py` est devenu la source de verite pour `PLUGIN_DATA`, `PLUGIN_ROOT`, `frontier.tsv`, les timestamps, les locks et les ecritures atomiques.
- `scripts/meta_harness.py` et `servers/mh_server.py` utilisent maintenant cette couche partagee.
- Les defaults runtime ont ete alignes sur `/tmp/meta-harness-lab`.

### 2. Validation et eval de base plus coherentes

- `cmd_validate()` couvre maintenant aussi `.mcp.json`.
- `scripts/eval_runner.py` ignore `_schema.json` au lieu de le traiter comme une vraie tache runnable.
- Le cache eval est centre sur la config partagee.

### 3. Promotion et reservations durcies

- `promote` refuse maintenant les promotions hors worktree git.
- `promote` bloque sur worktree sale, tag de securite deja existant, et `metrics.json` manquant ou invalide.
- `parallel-run` reserve maintenant des runs coherents: `metrics.json` valide, statut `reserved`, ligne frontier associee.
- `next-run` est aligne sur ce meme contrat sans reinitialiser un run deja existant.

### 4. Optionalite MCP corrigee

- `servers/mh_server.py` n'explose plus a l'import si `mcp` manque.
- Le serveur degrade proprement en stub a l'import et leve maintenant l'erreur seulement au demarrage effectif via `run_server()`.
- Une couverture de tests ciblee verifie explicitement ce comportement.

### 5. QA et portabilite ameliorees

- Le test context harvester n'utilise plus de chemin Windows hardcode.
- Une vraie CI GitHub Actions existe maintenant sous `.github/workflows/ci.yml`.
- La CI couvre Linux, Windows et macOS, plus un job dedie avec `mcp` installe.
- La suite locale est actuellement a 80 tests.

## Toujours ouverts

### 1. Semantique produit et source de verite metier

Le repo a encore trop de statuts qui racontent des choses voisines sans etre modeles ensemble:

- verdicts de rapport: `PROMOTE / REJECT / ITERATE`
- statuts frontier: `reserved / complete / promoted`
- statuts evaluateur LLM: `accepted / accepted_with_warnings / rejected / partial`

Il faut un modele metier unique, ou au minimum une table de mapping explicite et testee.

### 2. Metriques encore trop pauvres pour la promesse "scientifique"

Le stockage reste essentiellement scalar:

- pas de `sample_size`
- pas de `eval_method`
- pas de separation nette `deterministic_score` / `llm_judge_score`
- pas de variance, intervalle, seed, baseline, version de benchmark

La promesse evidence-oriented est vraie. La promesse "scientifique" forte reste trop ambitieuse sans enrichissement du schema.

### 3. `eval_runner.py` reste trop shell-centric

Le runner utilise encore `shell=True` pour les commandes. C'est pratique, mais pas ideal pour:

- la portabilite
- le quoting
- la securite si les taches deviennent moins trustees

Le prochain cran de robustesse est d'introduire une forme structuree de commande quand c'est possible, puis de normaliser les appels Python via `sys.executable` ou le wrapper du repo.

### 4. `context_harvester.py` peut encore gagner en rigueur

Le harvester est bon, mais il reste des sujets ouverts:

- meilleure observabilite des erreurs aujourd'hui silencieuses
- explicitation du poids exact des signaux dans le ranking final
- eventuelle consolidation du matching projet / memoire
- eventuel travail de chunking plus fin sur les gros fichiers

### 5. Packaging et imports encore pragmatiques

Le repo fonctionne, mais repose encore sur des `sys.path.insert()` dans plusieurs entrees Python. Ce n'est pas bloquant pour l'usage interne, mais c'est en dessous d'un packaging propre si l'objectif devient distribution ou reutilisation plus large.

### 6. Privacy / retention / logs

L'observabilite est utile, mais il manque encore une strategie claire sur:

- redaction
- retention
- chemins de stockage non ephemeres par defaut
- sensibilite des traces et des inputs/outils captures

## Priorites recommandees maintenant

1. Introduire un schema de metriques plus riche et versionne.
2. Unifier les statuts et verdicts metier dans un modele explicite.
3. Durcir `eval_runner.py` pour reduire la dependance a `shell=True`.
4. Ameliorer l'observabilite de `context_harvester.py` sans perdre sa tolerance aux erreurs.
5. Clarifier la story produit dans la doc: prerequis reels, limites, confidentialite, benchmark, cas d'usage.

## Ce que je garderais tel quel

- separation des roles
- principe de context break
- contrainte "max 3 files"
- traces et artifacts sur disque
- frontier de Pareto comme primitive de pilotage

## Phrase de synthese

Ce repo n'est pas un gadget. Ce n'est pas encore un systeme industrialise de mesure "scientifique" fort. C'est un bon socle d'ingenierie, maintenant sensiblement plus coherent qu'au moment du premier audit, avec encore quelques chantiers cles sur la semantique, les metriques, l'eval et l'ops.
