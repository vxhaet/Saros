RGPD_CATEGORIES = [
    # --- Article 4 : Données personnelles ---
    {
        "code": "NOM",
        "label": "Nom de famille",
        "article": "Article 4",
        "description": "Nom de famille, nom de naissance, nom de jeune fille, nom marital",
    },
    {
        "code": "PRENOM",
        "label": "Prénom",
        "article": "Article 4",
        "description": "Prénom, second prénom",
    },
    {
        "code": "EMAIL",
        "label": "Adresse email",
        "article": "Article 4",
        "description": "Adresse de courrier électronique",
    },
    {
        "code": "TELEPHONE",
        "label": "Numéro de téléphone",
        "article": "Article 4",
        "description": "Numéro de téléphone fixe ou mobile",
    },
    {
        "code": "ADRESSE",
        "label": "Adresse postale",
        "article": "Article 4",
        "description": "Adresse postale complète ou partielle (rue, ville, code postal, pays)",
    },
    {
        "code": "DATE_NAISS",
        "label": "Date de naissance",
        "article": "Article 4",
        "description": "Date de naissance, âge",
    },
    {
        "code": "NIR",
        "label": "Numéro de sécurité sociale",
        "article": "Article 4",
        "description": "Numéro d'inscription au répertoire (NIR), numéro de sécurité sociale",
    },
    {
        "code": "PASSEPORT",
        "label": "Numéro de passeport",
        "article": "Article 4",
        "description": "Numéro de passeport",
    },
    {
        "code": "CNI",
        "label": "Carte d'identité",
        "article": "Article 4",
        "description": "Numéro de carte d'identité nationale",
    },
    {
        "code": "PERMIS",
        "label": "Permis de conduire",
        "article": "Article 4",
        "description": "Numéro de permis de conduire",
    },
    {
        "code": "IP",
        "label": "Adresse IP",
        "article": "Article 4",
        "description": "Adresse IP, identifiant de connexion",
    },
    {
        "code": "GEOLOC",
        "label": "Géolocalisation",
        "article": "Article 4",
        "description": "Coordonnées GPS, données de localisation",
    },
    {
        "code": "IBAN",
        "label": "IBAN / Compte bancaire",
        "article": "Article 4",
        "description": "IBAN, numéro de compte bancaire, RIB, BIC",
    },
    {
        "code": "CB",
        "label": "Carte bancaire",
        "article": "Article 4",
        "description": "Numéro de carte de crédit ou de débit",
    },
    {
        "code": "SALAIRE",
        "label": "Salaire / Revenus",
        "article": "Article 4",
        "description": "Informations de rémunération, salaire, revenus",
    },
    {
        "code": "IMMAT",
        "label": "Immatriculation véhicule",
        "article": "Article 4",
        "description": "Numéro d'immatriculation de véhicule",
    },
    {
        "code": "PHOTO",
        "label": "Photo / Image",
        "article": "Article 4",
        "description": "Photographie ou image permettant d'identifier une personne",
    },
    {
        "code": "ID_UNIQUE",
        "label": "Identifiant unique",
        "article": "Article 4",
        "description": "Identifiant client, employé, matricule, numéro de dossier",
    },
    # --- Article 9 : Données sensibles ---
    {
        "code": "ETHNIE",
        "label": "Origine raciale ou ethnique",
        "article": "Article 9",
        "description": "Données révélant l'origine raciale ou ethnique",
    },
    {
        "code": "POLITIQUE",
        "label": "Opinions politiques",
        "article": "Article 9",
        "description": "Opinions politiques",
    },
    {
        "code": "RELIGION",
        "label": "Convictions religieuses",
        "article": "Article 9",
        "description": "Convictions religieuses ou philosophiques",
    },
    {
        "code": "SYNDICAT",
        "label": "Appartenance syndicale",
        "article": "Article 9",
        "description": "Appartenance à un syndicat",
    },
    {
        "code": "GENETIQUE",
        "label": "Données génétiques",
        "article": "Article 9",
        "description": "Données génétiques",
    },
    {
        "code": "BIOMETRIE",
        "label": "Données biométriques",
        "article": "Article 9",
        "description": "Données biométriques aux fins d'identification",
    },
    {
        "code": "SANTE",
        "label": "Données de santé",
        "article": "Article 9",
        "description": "Données concernant la santé physique ou mentale",
    },
    {
        "code": "SEXUALITE",
        "label": "Vie sexuelle / Orientation",
        "article": "Article 9",
        "description": "Données concernant la vie sexuelle ou l'orientation sexuelle",
    },
    # --- Article 10 : Données pénales ---
    {
        "code": "PENAL",
        "label": "Données pénales",
        "article": "Article 10",
        "description": "Condamnations pénales et infractions",
    },
]


def get_categories_for_prompt() -> str:
    lines = []
    for cat in RGPD_CATEGORIES:
        lines.append(
            f"- Code: {cat['code']} | {cat['label']} ({cat['article']}) : {cat['description']}"
        )
    return "\n".join(lines)
