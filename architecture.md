# Architecture et fonctionnement de l’application

## 1. Objectif de l’application

Le but de l’application est d’interfacer une demande utilisateur sous forme de texte et de la traduire en action à l’intérieur de l’organisation.

L’architecture sera composée de plusieurs couches.

## 2. Interface utilisateur

L’interface utilisateur recueillera les demandes sous forme de texte et les transmettra au service de traitement.

Les interfaces utilisateur seront développées en **Flutter / Dart**.

## 3. Service d’aiguillage

Un service central collectera la demande utilisateur et l’aiguillera vers le bon module en fonction du type de question ou de demande.

L’aiguillage sera réalisé à partir d’une **table de paramètres**, permettant de déterminer le module à utiliser en fonction de la demande reçue.

## 4. Modules fonctionnels

Chaque module disposera de son propre contexte et d’un domaine de fonctionnalité déterminé.

### 4.1. Module d’anonymisation

Ce module reçoit les demandes d’anonymisation.

Il aura pour rôle de :

- rechercher les données devant être anonymisées ;
- réaliser le cryptage ou l’anonymisation des données ;
- transmettre les données nettoyées à un agent AI.

### 4.2. Module de reporting

Ce module permet de recevoir les demandes de reporting et de les traduire en requêtes SQL vers les bases de données internes.

Son rôle est de :

- analyser la demande utilisateur ;
- générer la requête SQL correspondante ;
- interroger la base de données interne ;
- construire le rapport ;
- retourner le résultat à l’utilisateur.

### 4.3. Module de correspondance

Ce module permet de réaliser des mappings entre différents fichiers.

Il connaîtra notamment :

- le contexte du fichier source ;
- le contexte du fichier destination ;
- les règles de correspondance entre les différentes données.

Il pourra ainsi déterminer comment transformer les données du format source vers le format destination.

### 4.4. Module de correction des données

Ce module reçoit en entrée une table provenant de la base de données locale.

Il analyse les données afin de proposer des corrections de format et d'améliorer leur qualité.

Son rôle pourra notamment être de :

- détecter les incohérences de format ;
- identifier les valeurs potentiellement incorrectes ;
- proposer des corrections ;
- produire un résultat contenant les données corrigées ou les corrections proposées.

## 5. Actions des modules

Chaque module disposera d’une liste d’actions qu’il est capable d’exécuter.

Ces actions seront définies dans une **table de paramètres**.

Cette approche permettra de modifier ou d’ajouter des actions sans devoir modifier directement le fonctionnement général de l’application.

La table de paramètres permettra notamment de définir :

- les actions disponibles ;
- le module auquel elles appartiennent ;
- leur contexte ;
- les paramètres nécessaires à leur exécution ;
- éventuellement les règles permettant de déterminer dans quelles situations elles doivent être utilisées.

## 6. Retour vers l’utilisateur

Le résultat du traitement sera retourné par le module concerné.

Le traitement pourra être :

- **synchrone**, lorsque la demande peut être traitée immédiatement ;
- **asynchrone**, lorsque le traitement nécessite davantage de temps ou une intervention ultérieure.

Les échanges entre les différents composants de l’application utiliseront un format **JSON**.

L’architecture générale sera donc basée sur le principe suivant :

```text
Utilisateur
    │
    ▼
Interface Flutter / Dart
    │
    ▼
Service de collecte et d’aiguillage
    │
    │
    ├──► Module d’anonymisation
    │
    ├──► Module de reporting
    │
    ├──► Module de correspondance
    │
    └──► Module de correction des données
             │
             ▼
       Actions définies
       dans les paramètres
             │
             ▼
       Traitement synchrone
       ou asynchrone
             │
             ▼
        Résultat JSON
             │
             ▼
       Interface utilisateur
```

L’objectif global est ainsi de disposer d’une architecture modulaire dans laquelle une demande formulée naturellement par l’utilisateur peut être analysée, orientée vers le module approprié et transformée en une ou plusieurs actions concrètes au sein de l’organisation.
