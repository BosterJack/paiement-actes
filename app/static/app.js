"use strict";

const etat = { jeton: null, nom: null, demandeSelectionnee: null };

function lireSession() {
  try {
    etat.jeton = localStorage.getItem("jeton");
    etat.nom = localStorage.getItem("nom");
  } catch (_) { /* stockage indisponible : on redemande le nom */ }
}

function enregistrerSession(jeton, nom) {
  etat.jeton = jeton;
  etat.nom = nom;
  try {
    localStorage.setItem("jeton", jeton);
    localStorage.setItem("nom", nom);
  } catch (_) {}
}

async function api(methode, chemin, corps, entetes = {}) {
  const options = { method: methode, headers: { ...entetes } };
  if (etat.jeton) options.headers.Authorization = `Bearer ${etat.jeton}`;
  if (corps !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(corps);
  }
  const r = await fetch(chemin, options);
  const donnees = r.status === 204 ? null : await r.json();
  if (!r.ok) {
    const detail = Array.isArray(donnees?.detail)
      ? donnees.detail.map((d) => d.msg).join(", ")
      : donnees?.detail;
    throw new Error(detail || `Erreur ${r.status}`);
  }
  return donnees;
}

// Petit utilitaire DOM : textContent partout, donc pas d'injection HTML.
function el(tag, attributs = {}, ...enfants) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attributs)) {
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else e.setAttribute(k, v);
  }
  for (const enfant of enfants) e.append(enfant instanceof Node ? enfant : String(enfant));
  return e;
}

const badge = (statut) => el("span", { class: `badge ${statut}` }, statut.replaceAll("_", " "));
const $ = (id) => document.getElementById(id);

function message(id, texte, erreur = false) {
  $(id).textContent = texte;
  $(id).className = `message ${erreur ? "erreur" : ""}`;
}

let libelles = {};

async function chargerTypesActes() {
  const types = await api("GET", "/api/types-actes");
  $("type-acte").replaceChildren(
    ...types.map((t) => {
      libelles[t.code] = t.libelle;
      return el("option", { value: t.code }, `${t.libelle} — ${t.tarif_unitaire} FCFA`);
    })
  );
}

async function afficherDemandes() {
  const demandes = await api("GET", "/api/demandes");
  $("liste-demandes").replaceChildren(
    ...demandes.map((d) =>
      el("tr", {},
        el("td", {}, d.id),
        el("td", {}, libelles[d.type_acte] || d.type_acte),
        el("td", {}, d.nombre_copies),
        el("td", {}, `${d.montant} FCFA`),
        el("td", {}, badge(d.statut)),
        el("td", {}, el("button", { class: "secondaire", onclick: () => selectionnerDemande(d) },
          d.statut === "PAYEE" ? "Voir" : "Payer"))
      )
    )
  );
}

async function selectionnerDemande(demande) {
  etat.demandeSelectionnee = demande;
  $("bloc-paiement").classList.remove("cache");
  $("paiement-demande-id").textContent = demande.id;
  $("paiement-montant").textContent = demande.montant;
  $("form-paiement").classList.toggle("cache", demande.statut === "PAYEE");
  message("msg-paiement", "");
  await afficherPaiements();
}

async function afficherPaiements() {
  const demande = etat.demandeSelectionnee;
  if (!demande) return;
  const paiements = await api("GET", `/api/demandes/${demande.id}/paiements`);
  $("liste-paiements").replaceChildren(
    ...paiements.map((p) =>
      el("tr", {},
        el("td", {}, p.id),
        el("td", {}, p.operateur),
        el("td", {}, p.telephone),
        el("td", {}, `${p.montant} FCFA`),
        el("td", {}, badge(p.statut), p.motif ? el("div", { class: "aide" }, p.motif) : "")
      )
    )
  );
  const payee = paiements.some((p) => p.statut === "REUSSI");
  $("form-paiement").classList.toggle("cache", payee);
  $("btn-payer").disabled = paiements.some((p) => p.statut === "EN_COURS");
}

async function payer(evenement) {
  evenement.preventDefault();
  const demande = etat.demandeSelectionnee;
  // Une clé par clic : si le réseau coupe, on renvoie la MÊME clé, donc un seul débit.
  const cle = crypto.randomUUID();
  const corps = {
    telephone: $("telephone").value.replace(/\s/g, ""),
    operateur: $("operateur").value,
  };
  $("btn-payer").disabled = true;
  for (let essai = 1; essai <= 3; essai++) {
    try {
      const p = await api("POST", `/api/demandes/${demande.id}/paiements`, corps, { "Idempotency-Key": cle });
      message("msg-paiement", `Débit demandé à ${p.operateur} : validez sur votre téléphone.`);
      break;
    } catch (e) {
      const coupureReseau = e instanceof TypeError;
      if (!coupureReseau || essai === 3) {
        message("msg-paiement", e.message, true);
        break;
      }
    }
  }
  await rafraichir();
}

async function afficherSimulateur() {
  const debits = await api("GET", "/simulateur/debits");
  const action = (reference, chemin, corps) => async () => {
    try {
      await api("POST", `/simulateur/debits/${reference}/${chemin}`, corps);
    } catch (e) {
      alert(e.message);
    }
    await rafraichir();
  };
  $("liste-debits").replaceChildren(
    ...debits.map((d) =>
      el("tr", {},
        el("td", {}, el("div", {}, `${d.operateur} ${d.telephone}`), el("div", {}, `${d.montant} FCFA`),
          el("div", { class: "aide" }, `réf. ${d.reference.slice(0, 8)}…`)),
        el("td", {}, ...d.envois.map((e) =>
          el("div", { class: "aide" }, `${e.resultat} (${e.signature}) → HTTP ${e.reponse_du_service.code_http}`))),
        el("td", { class: "actions" },
          el("button", { onclick: action(d.reference, "resultat", { resultat: "REUSSI" }) }, "Réussite"),
          el("button", { onclick: action(d.reference, "resultat", { resultat: "ECHOUE" }) }, "Échec"),
          el("button", { class: "secondaire", onclick: action(d.reference, "renvoyer") }, "Renvoyer"),
          el("button", { class: "secondaire",
            onclick: action(d.reference, "resultat", { resultat: "REUSSI", signature_valide: false }) },
            "Signature falsifiée"))
      )
    )
  );
}

async function rafraichir() {
  try {
    await Promise.all([afficherDemandes(), afficherPaiements(), afficherSimulateur()]);
  } catch (e) {
    if (e.message.includes("Jeton")) deconnecter();
  }
}

function deconnecter() {
  try { localStorage.clear(); } catch (_) {}
  location.reload();
}

async function demarrer() {
  $("bloc-inscription").classList.add("cache");
  $("bloc-usager").classList.remove("cache");
  $("usager-actuel").replaceChildren(
    `Connecté : ${etat.nom} `,
    el("button", { class: "secondaire", onclick: deconnecter }, "Changer d'usager")
  );
  await chargerTypesActes();
  await rafraichir();
  setInterval(rafraichir, 2000); // suit l'arrivée du résultat de l'opérateur
}

$("form-inscription").addEventListener("submit", async (e) => {
  e.preventDefault();
  const u = await api("POST", "/api/usagers", { nom: $("nom").value });
  enregistrerSession(u.jeton, u.nom);
  await demarrer();
});

$("form-demande").addEventListener("submit", async (e) => {
  e.preventDefault();
  try {
    const d = await api("POST", "/api/demandes", {
      type_acte: $("type-acte").value,
      nombre_copies: Number($("copies").value),
    });
    message("msg-demande", `Demande n° ${d.id} enregistrée : ${d.montant} FCFA à payer.`);
    await afficherDemandes();
    await selectionnerDemande(d);
  } catch (err) {
    message("msg-demande", err.message, true);
  }
});

$("form-paiement").addEventListener("submit", payer);

lireSession();
if (etat.jeton) demarrer();
afficherSimulateur();
