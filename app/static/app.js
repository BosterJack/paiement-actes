"use strict";

const ICONES = {
  ACTE_NAISSANCE: "bi-person-vcard",
  CASIER_JUDICIAIRE: "bi-shield-check",
  CERTIFICAT_RESIDENCE: "bi-house-door",
};
const LIBELLES_STATUT = {
  EN_ATTENTE_PAIEMENT: "À payer",
  PAYEE: "Payée",
  EN_COURS: "En cours",
  REUSSI: "Réussi",
  ECHOUE: "Échoué",
  EXPIRE: "Expiré",
};
const FRAIS_SERVICE = 100;

const etat = { jeton: null, nom: null, types: [], demandes: [], demandeOuverte: null, debitsVus: new Set() };
const $ = (id) => document.getElementById(id);
const fcfa = (n) => new Intl.NumberFormat("fr-FR").format(n);

// ---------- Session (stockage local facultatif) ----------
function lireSession() {
  try {
    etat.jeton = localStorage.getItem("jeton");
    etat.nom = localStorage.getItem("nom");
  } catch (_) {}
}
function enregistrerSession(jeton, nom) {
  Object.assign(etat, { jeton, nom });
  try {
    localStorage.setItem("jeton", jeton);
    localStorage.setItem("nom", nom);
  } catch (_) {}
}
function deconnecter() {
  try { localStorage.removeItem("jeton"); localStorage.removeItem("nom"); } catch (_) {}
  location.reload();
}

// ---------- Appels API ----------
async function api(methode, chemin, corps, entetes = {}) {
  const options = { method: methode, headers: { ...entetes } };
  if (etat.jeton) options.headers.Authorization = `Bearer ${etat.jeton}`;
  if (corps !== undefined) {
    options.headers["Content-Type"] = "application/json";
    options.body = JSON.stringify(corps);
  }
  const r = await fetch(chemin, options);
  const donnees = await r.json().catch(() => null);
  if (!r.ok) {
    const detail = Array.isArray(donnees?.detail)
      ? donnees.detail.map((d) => d.msg).join(", ")
      : donnees?.detail;
    const err = new Error(detail || `Erreur ${r.status}`);
    err.status = r.status;
    throw err;
  }
  return donnees;
}

// ---------- DOM : textContent partout, donc pas d'injection HTML ----------
function el(tag, attributs = {}, ...enfants) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attributs)) {
    if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (v !== false && v != null) e.setAttribute(k, v === true ? "" : v);
  }
  for (const enfant of enfants.flat()) {
    if (enfant == null || enfant === false) continue;
    e.append(enfant instanceof Node ? enfant : String(enfant));
  }
  return e;
}
const icone = (classe) => el("i", { class: `bi ${classe}` });
const pastille = (statut) => el("span", { class: `statut s-${statut}` }, LIBELLES_STATUT[statut] || statut);

function toast(message, type = "primary", ic = "bi-info-circle-fill") {
  const t = el("div", { class: `toast align-items-center text-bg-${type} border-0`, role: "status" },
    el("div", { class: "d-flex" },
      el("div", { class: "toast-body d-flex gap-2 align-items-center" }, icone(ic), message),
      el("button", { type: "button", class: "btn-close btn-close-white me-2 m-auto", "data-bs-dismiss": "toast" })));
  $("toasts").append(t);
  const bt = new bootstrap.Toast(t, { delay: 4000 });
  t.addEventListener("hidden.bs.toast", () => t.remove());
  bt.show();
}

// ---------- Nouvelle demande ----------
function typeChoisi() {
  const code = document.querySelector('input[name="type"]:checked')?.value;
  return etat.types.find((t) => t.code === code);
}

function afficherTypes() {
  $("types-actes").replaceChildren(...etat.types.map((t, i) => [
    el("input", { type: "radio", class: "btn-check", name: "type", id: `type-${t.code}`, value: t.code, checked: i === 0, onchange: majRecap }),
    el("label", { class: "type-acte", for: `type-${t.code}` },
      el("span", { class: "icone" }, icone(ICONES[t.code] || "bi-file-earmark")),
      el("span", {}, el("div", { class: "fw-semibold" }, t.libelle), el("div", { class: "small text-secondary" }, "par copie")),
      el("span", { class: "prix" }, `${fcfa(t.tarif_unitaire)} FCFA`)),
  ]).flat());
  majRecap();
}

function majRecap() {
  const t = typeChoisi();
  const copies = Math.min(20, Math.max(1, Number($("copies").value) || 1));
  if (!t) return;
  $("recap-ligne").textContent = `${t.libelle} × ${copies}`;
  $("recap-sous-total").textContent = `${fcfa(t.tarif_unitaire * copies)} FCFA`;
  $("recap-total").textContent = `${fcfa(t.tarif_unitaire * copies + FRAIS_SERVICE)} FCFA`;
}

function changerCopies(delta) {
  $("copies").value = Math.min(20, Math.max(1, (Number($("copies").value) || 1) + delta));
  majRecap();
}

async function creerDemande(e) {
  e.preventDefault();
  try {
    const d = await api("POST", "/api/demandes", {
      type_acte: typeChoisi().code,
      nombre_copies: Number($("copies").value),
    });
    toast(`Demande n° ${d.id} enregistrée : ${fcfa(d.montant)} FCFA à payer`, "success", "bi-check-circle-fill");
    await chargerDemandes();
    ouvrirPaiement(d);
  } catch (err) {
    toast(err.message, "danger", "bi-exclamation-triangle-fill");
  }
}

// ---------- Mes demandes ----------
const libelle = (code) => etat.types.find((t) => t.code === code)?.libelle || code;

async function chargerDemandes() {
  etat.demandes = await api("GET", "/api/demandes");
  const d = etat.demandes;
  $("stat-total").textContent = d.length;
  $("stat-attente").textContent = d.filter((x) => x.statut !== "PAYEE").length;
  $("stat-payees").textContent = d.filter((x) => x.statut === "PAYEE").length;
  $("stat-montant").textContent = fcfa(d.filter((x) => x.statut === "PAYEE").reduce((s, x) => s + x.montant, 0));
  $("vide").classList.toggle("d-none", d.length > 0);
  $("liste-demandes").replaceChildren(...d.map((x) =>
    el("div", { class: "demande" },
      el("span", { class: "icone" }, icone(ICONES[x.type_acte] || "bi-file-earmark")),
      el("div", { class: "infos" },
        el("div", { class: "fw-semibold text-truncate" }, libelle(x.type_acte)),
        el("div", { class: "small text-secondary" },
          `N° ${x.id} · ${x.nombre_copies} copie${x.nombre_copies > 1 ? "s" : ""} · ${new Date(x.cree_le + "Z").toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" })}`)),
      el("div", { class: "text-end" },
        el("div", { class: "fw-bold" }, `${fcfa(x.montant)} FCFA`), pastille(x.statut)),
      x.statut === "PAYEE"
        ? el("button", { class: "btn btn-sm btn-outline-secondary", onclick: () => ouvrirPaiement(x), title: "Détails" }, icone("bi-receipt"))
        : el("button", { class: "btn btn-sm btn-primary", onclick: () => ouvrirPaiement(x) }, icone("bi-wallet2"), " Payer"))));
  // La fenêtre ouverte suit la demande à jour.
  if (etat.demandeOuverte) etat.demandeOuverte = d.find((x) => x.id === etat.demandeOuverte.id) || etat.demandeOuverte;
}

// ---------- Paiement ----------
const modal = () => bootstrap.Modal.getOrCreateInstance($("modal-paiement"));

const chiffresTelephone = () => $("telephone").value.replace(/\D/g, "");

// Masque de saisie : chiffres uniquement, 10 au maximum, affichés « 01 97 12 34 56 ».
function formaterTelephone() {
  const champ = $("telephone");
  const chiffres = chiffresTelephone().slice(0, 10);
  champ.value = chiffres.replace(/(\d{2})(?=\d)/g, "$1 ");

  const debutFaux = chiffres.length >= 2 ? !chiffres.startsWith("01") : chiffres.length === 1 && chiffres !== "0";
  const complet = chiffres.length === 10 && !debutFaux;
  const groupe = champ.closest(".telephone-groupe");
  groupe.classList.toggle("valide", complet);
  groupe.classList.toggle("invalide", debutFaux);
  $("compteur-telephone").replaceChildren(complet ? icone("bi-check-circle-fill") : `${chiffres.length}/10`);

  const aide = $("aide-telephone");
  if (debutFaux) {
    aide.textContent = "Le numéro doit commencer par 01.";
    aide.className = "form-text mb-3 text-danger";
  } else if (complet) {
    aide.textContent = "Numéro valide.";
    aide.className = "form-text mb-3 text-success";
  } else {
    aide.textContent = `Encore ${10 - chiffres.length} chiffre(s) : 10 chiffres, commence par 01.`;
    aide.className = "form-text mb-3";
  }
  $("btn-payer").disabled = !complet;
}

// Bloque toute frappe autre qu'un chiffre (le collage est nettoyé par formaterTelephone).
function filtrerTouche(e) {
  if (e.ctrlKey || e.metaKey || e.altKey || e.key.length > 1) return;
  const remplaceSelection = e.target.selectionEnd > e.target.selectionStart;
  if (!/[0-9]/.test(e.key) || (chiffresTelephone().length >= 10 && !remplaceSelection)) e.preventDefault();
}

function ouvrirPaiement(demande) {
  etat.demandeOuverte = demande;
  $("modal-acte").textContent = `${libelle(demande.type_acte)} · ${demande.nombre_copies} copie(s) · demande n° ${demande.id}`;
  $("modal-montant").textContent = fcfa(demande.montant);
  $("btn-montant").textContent = fcfa(demande.montant);
  $("telephone").value = "";
  formaterTelephone();
  $("suivi").classList.add("d-none");
  $("historique").replaceChildren();
  modal().show();
  chargerPaiements();
}

function blocSuivi(p) {
  const config = {
    EN_COURS: ["en-cours", el("div", { class: "spinner-border text-primary", style: "width:3rem;height:3rem" }),
      "En attente de validation", `Validez le débit de ${fcfa(p.montant)} FCFA sur le ${p.telephone} (${p.operateur}).`],
    REUSSI: ["reussi", el("i", { class: "bi bi-check-circle-fill text-success grande-icone" }),
      "Paiement réussi", "Votre demande est payée. Merci !"],
    ECHOUE: ["echoue", el("i", { class: "bi bi-x-circle-fill text-danger grande-icone" }),
      "Paiement échoué", p.motif || "Le débit a été refusé. Vous pouvez réessayer."],
    EXPIRE: ["echoue", el("i", { class: "bi bi-clock-history text-danger grande-icone" }),
      "Aucune réponse de l'opérateur", "Le délai est dépassé. Vous pouvez réessayer."],
  }[p.statut];
  const fini = p.statut !== "EN_COURS";
  const marque = (ok, texte) => el("span", { class: ok === true ? "ok" : ok === false ? "ko" : "" },
    icone(ok === true ? "bi-check-circle-fill" : ok === false ? "bi-x-circle-fill" : "bi-circle"), " ", texte);
  return el("div", { class: `suivi ${config[0]}` },
    config[1],
    el("div", { class: "fw-bold fs-5 mt-2" }, config[2]),
    el("div", { class: "text-secondary small" }, config[3]),
    el("div", { class: "etapes" },
      marque(true, "Débit demandé"),
      marque(true, "Reçu par l'opérateur"),
      marque(fini ? p.statut === "REUSSI" : null, fini ? LIBELLES_STATUT[p.statut] : "Résultat")));
}

async function chargerPaiements() {
  const d = etat.demandeOuverte;
  if (!d) return;
  const paiements = await api("GET", `/api/demandes/${d.id}/paiements`);
  const dernier = paiements[0];
  const precedent = $("suivi").dataset.statut;
  $("suivi").classList.toggle("d-none", !dernier);
  if (dernier) {
    $("suivi").replaceChildren(blocSuivi(dernier));
    $("suivi").dataset.statut = `${dernier.id}:${dernier.statut}`;
    if (precedent === `${dernier.id}:EN_COURS` && dernier.statut === "REUSSI") toast("Paiement réussi 🎉", "success", "bi-check-circle-fill");
    if (precedent === `${dernier.id}:EN_COURS` && ["ECHOUE", "EXPIRE"].includes(dernier.statut)) toast("Paiement non abouti", "danger", "bi-x-circle-fill");
  }
  const bloque = paiements.some((p) => ["EN_COURS", "REUSSI"].includes(p.statut));
  $("form-paiement").classList.toggle("d-none", bloque);
  $("historique").replaceChildren(...(paiements.length ? [
    el("div", { class: "small text-uppercase fw-semibold text-secondary mb-1" }, "Historique des tentatives"),
    ...paiements.map((p) => el("div", { class: "ligne-paiement" },
      el("span", {}, el("span", { class: "fw-semibold" }, `#${p.id} ${p.operateur}`), el("span", { class: "text-secondary" }, ` · ${p.telephone}`)),
      pastille(p.statut))),
  ] : []));
}

async function payer(e) {
  e.preventDefault();
  const d = etat.demandeOuverte;
  const telephone = chiffresTelephone();
  if (!/^01[0-9]{8}$/.test(telephone)) {
    formaterTelephone();
    return;
  }
  const corps = { telephone, operateur: document.querySelector('input[name="operateur"]:checked').value };
  // Une clé par clic : si le réseau coupe, on renvoie la MÊME clé, donc un seul débit.
  const cle = crypto.randomUUID();
  const bouton = $("btn-payer");
  bouton.disabled = true;
  bouton.replaceChildren(el("span", { class: "spinner-border spinner-border-sm me-2" }), "Envoi…");
  try {
    for (let essai = 1; essai <= 3; essai++) {
      try {
        await api("POST", `/api/demandes/${d.id}/paiements`, corps, { "Idempotency-Key": cle });
        toast(`Débit demandé à ${corps.operateur}`, "primary", "bi-phone-vibrate");
        break;
      } catch (err) {
        const coupureReseau = err instanceof TypeError;
        if (!coupureReseau || essai === 3) throw err;
      }
    }
  } catch (err) {
    toast(err.message, "danger", "bi-exclamation-triangle-fill");
  } finally {
    bouton.replaceChildren(icone("bi-lock-fill"), " Payer ",
      el("span", { id: "btn-montant" }, fcfa(d.montant)), " FCFA");
    formaterTelephone();
  }
  await Promise.all([chargerPaiements(), chargerDemandes(), chargerDebits()]);
}

// ---------- Console du simulateur ----------
async function actionSimulateur(reference, chemin, corps, texte) {
  try {
    const envoi = await api("POST", `/simulateur/debits/${reference}/${chemin}`, corps);
    const code = envoi.reponse_du_service.code_http;
    toast(`${texte} → le service répond HTTP ${code}`, code === 200 ? "dark" : "warning", "bi-broadcast");
  } catch (err) {
    toast(err.message, "warning", "bi-exclamation-triangle-fill");
  }
  await rafraichir();
}

const LIBELLES_MODE = {
  NUMERO: "selon le numéro (…00 échec, …99 sans réponse, sinon réussite)",
  REUSSITE: "toujours réussite",
  ECHEC: "toujours échec",
  MANUEL: "manuel, choisissez le résultat dans le simulateur",
};

function afficherMode(mode) {
  const radio = $(`mode-${mode}`);
  if (radio) radio.checked = true;
}

async function changerMode(e) {
  const { mode } = await api("PUT", "/simulateur/mode", { mode: e.target.value });
  afficherMode(mode);
  toast(`Simulateur : ${LIBELLES_MODE[mode]}`, "dark", "bi-sliders");
}

async function chargerDebits() {
  afficherMode((await api("GET", "/simulateur/mode")).mode);
  const debits = await api("GET", "/simulateur/debits");
  const sansReponse = debits.filter((d) => d.envois.length === 0).length;
  $("badge-debits").textContent = sansReponse;
  $("badge-debits").classList.toggle("d-none", sansReponse === 0);
  $("debits-vide").classList.toggle("d-none", debits.length > 0);
  $("liste-debits").replaceChildren(...debits.map((d) =>
    el("div", { class: "debit" },
      el("div", { class: "d-flex justify-content-between align-items-start" },
        el("div", {},
          el("div", { class: "montant" }, `${fcfa(d.montant)} FCFA`),
          el("div", { class: "small opacity-75" }, `${d.operateur} · ${d.telephone}`),
          el("div", { class: "small opacity-50" }, `réf. ${d.reference.slice(0, 12)}…`)),
        el("span", { class: "badge text-bg-secondary" }, d.id_transaction)),
      d.envois.length === 0
        ? el("div", { class: "envoi text-warning" }, "⏳ en attente d'un résultat")
        : d.envois.map((e) => el("div", { class: `envoi ${e.reponse_du_service.code_http === 200 ? "text-success" : "text-danger"}` },
          `${e.resultat} · signature ${e.signature} → HTTP ${e.reponse_du_service.code_http}`)),
      el("div", { class: "d-flex flex-wrap gap-1 mt-2" },
        el("button", { class: "btn btn-success btn-sm", onclick: () => actionSimulateur(d.reference, "resultat", { resultat: "REUSSI" }, "Réussite envoyée") }, icone("bi-check-lg"), " Réussite"),
        el("button", { class: "btn btn-danger btn-sm", onclick: () => actionSimulateur(d.reference, "resultat", { resultat: "ECHOUE" }, "Échec envoyé") }, icone("bi-x-lg"), " Échec"),
        el("button", { class: "btn btn-outline-light btn-sm", onclick: () => actionSimulateur(d.reference, "renvoyer", undefined, "Résultat renvoyé") }, icone("bi-arrow-repeat"), " Renvoyer"),
        el("button", { class: "btn btn-outline-warning btn-sm", onclick: () => actionSimulateur(d.reference, "resultat", { resultat: "REUSSI", signature_valide: false }, "Signature falsifiée envoyée") }, icone("bi-incognito"), " Signature falsifiée")))));
}

// ---------- Démarrage ----------
async function rafraichir() {
  try {
    const taches = [chargerDebits()];
    if (etat.jeton) taches.push(chargerDemandes());
    if (etat.jeton && $("modal-paiement").classList.contains("show")) taches.push(chargerPaiements());
    await Promise.all(taches);
  } catch (err) {
    if (err.status === 401) deconnecter();
  }
}

async function demarrer() {
  $("ecran-accueil").classList.add("d-none");
  $("ecran-tableau").classList.remove("d-none");
  $("zone-usager").classList.replace("d-none", "d-flex");
  $("nom-usager").textContent = etat.nom;
  $("prenom").textContent = etat.nom.split(" ")[0];
  $("avatar").textContent = etat.nom.trim().charAt(0).toUpperCase();
  etat.types = await api("GET", "/api/types-actes");
  afficherTypes();
  await rafraichir();
}

async function ouvrirSession(chemin, corps) {
  $("erreur-accueil").classList.add("d-none");
  try {
    const u = await api("POST", chemin, corps);
    enregistrerSession(u.jeton, u.nom);
    await demarrer();
  } catch (err) {
    $("erreur-accueil").textContent = err.message;
    $("erreur-accueil").classList.remove("d-none");
  }
}

$("form-connexion").addEventListener("submit", (e) => {
  e.preventDefault();
  ouvrirSession("/api/sessions", {
    identifiant: $("identifiant").value.trim(),
    mot_de_passe: $("mdp-connexion").value,
  });
});
$("form-inscription").addEventListener("submit", (e) => {
  e.preventDefault();
  ouvrirSession("/api/usagers", {
    nom: $("nom").value.trim(),
    npi: $("npi").value,
    email: $("email").value.trim(),
    mot_de_passe: $("mdp-inscription").value,
  });
});
$("npi").addEventListener("input", (e) => { e.target.value = e.target.value.replace(/\D/g, "").slice(0, 10); });
$("form-demande").addEventListener("submit", creerDemande);
$("form-paiement").addEventListener("submit", payer);
$("telephone").addEventListener("input", formaterTelephone);
document.querySelectorAll('input[name="mode"]').forEach((r) => r.addEventListener("change", changerMode));
$("telephone").addEventListener("keydown", filtrerTouche);
$("copies").addEventListener("input", majRecap);
$("moins").addEventListener("click", () => changerCopies(-1));
$("plus").addEventListener("click", () => changerCopies(1));
$("btn-deconnexion").addEventListener("click", deconnecter);
$("modal-paiement").addEventListener("hidden.bs.modal", () => { etat.demandeOuverte = null; });

lireSession();
if (etat.jeton) demarrer().catch(() => deconnecter());
rafraichir();
setInterval(rafraichir, 2000); // suit l'arrivée du résultat de l'opérateur
