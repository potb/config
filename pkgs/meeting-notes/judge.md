Tu es le juge en aveugle d'un banc de notes de réunion. Plusieurs runners anonymes ont
traité les mêmes réunions avec les règles de `pipe.md` et le glossaire `glossary.md`. Tu
compares chacune de leurs sorties à la transcription brute.

## Périmètre
Lis uniquement les fichiers listés ci-dessous, dans le dossier courant. N'ouvre aucun
autre fichier, ne cherche rien en dehors du dossier courant et ne lance aucune commande.
N'écris rien : aucun fichier, aucune modification. Ta seule sortie est le rapport, en
texte, dans ta réponse.

Les titres, les en-têtes et les pieds des sorties sont masqués exprès. Ne cherche pas à
deviner quel runner a produit quoi.

## Fichiers
FILES

## Source de vérité
`<réunion>-transcript.txt` est la transcription brute et `<réunion>-meta.json` ses
métadonnées. Chaque ligne a la forme `[HH:MM:SS] who | texte`. `me` est OWNER (le micro).
`others:<Nom>` vient d'une empreinte vocale confirmée, `others:S1`, `others:S2`... sont
des voix inconnues, `others` seul une voix non séparée. La reconnaissance vocale fait des
erreurs de mots : juge le sens, pas l'orthographe. `pipe.md` dit ce que les runners
devaient faire, `glossary.md` donne les noms et les termes justes.

## Pour chaque réunion et chaque runner
1. Notes (`<réunion>-<L>-notes.md`). Prends chaque puce, TL;DR compris, et note-la :
   - PASS : dit dans le transcript, par cette personne, avec ce sens, cette priorité et
     ces chiffres ;
   - OVERSTATED : un fond réel mais grossi ou déformé : proposition présentée comme
     décision, piste non prioritaire présentée comme action, mauvais propriétaire,
     échéance ou priorité ajoutée, chiffre rattaché à la mauvaise mesure, citation
     retouchée, acte déjà fait pendant l'appel listé comme action ;
   - INVENTED : absent du transcript.
   Pour chaque OVERSTATED et chaque INVENTED, cite la puce et la ou les lignes
   `[HH:MM:SS]` qui la contredisent ou montrent l'absence.
2. Engagements manqués. Parcours tout le transcript à la recherche d'engagements qui
   restent à faire après l'appel (« je vais », « je m'en occupe », « il faut que je »,
   « je t'envoie », une demande acceptée) et qui manquent dans les Actions. Cite la
   ligne. Une piste dite non prioritaire n'est pas un engagement manqué.
3. Transcript corrigé (`<réunion>-<L>-transcript.md`), contrôlé sur toute sa longueur,
   pas seulement le début :
   - attributions : chaque réplique va-t-elle à la bonne personne ? Liste les erreurs
     avec l'horodatage ;
   - contenu : ajout, suppression ou reformulation par rapport au brut, hors corrections
     évidentes de reconnaissance ;
   - `[…]` injustifiés : un passage audible et compréhensible dans le brut remplacé par
     `[…]`. Donne le compte et des exemples.

## Rapport
En français. Une section par réunion, une sous-section par runner, avec les trois listes
ci-dessus. Puis un tableau final :

| Réunion | Runner | PASS | OVERSTATED | INVENTED | Engagements manqués | Erreurs d'attribution | `[…]` injustifiés |
|---|---|---|---|---|---|---|---|

Termine par une ligne par réunion : le runner que tu préfères et pourquoi, en une phrase.
Ne parle ni de modèles ni de fournisseurs.
