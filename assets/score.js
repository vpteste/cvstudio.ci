/* ============================================================
   CV Studio — Scorer de CV côté client (heuristique, sans IA).
   Gratuit, hors-ligne, aucun envoi de données. Partagé par l'app
   (panneau Score) et la page /analyser-cv/ (analyseur ATS).
   Usage : CVScore.score(data, jobText) -> { scores, recommendations, keywords }
   ============================================================ */
window.CVScore = (function () {
  const clamp = n => Math.max(0, Math.min(100, Math.round(n)));

  const STOP = new Set(("le la les un une des du de et en au aux pour avec dans sur par sans sous vous nous notre votre vos nos est sont être avoir plus cette ces leur sera poste profil mission missions candidat candidate entreprise experience expérience competences compétences ans mois cdd cdi").split(" "));

  function score(data, jobText) {
    data = data || {};
    jobText = (jobText || "").toLowerCase();
    const exp = data.experiences || [], skills = data.skills || [], edu = data.education || [];
    const recs = [];

    // --- Présentation / complétude ---
    let contact = 0;
    ["fullName", "title", "email", "phone"].forEach(k => { if ((data[k] || "").trim()) contact++; });
    const presentation = clamp(40 + contact * 15);
    if (!(data.title || "").trim()) recs.push("Ajoutez un titre de poste clair sous votre nom.");
    if (!(data.email || "").trim() || !(data.phone || "").trim()) recs.push("Complétez vos coordonnées (email + téléphone).");

    // --- Lisibilité ---
    const sumLen = (data.summary || "").trim().length;
    let readability = 60;
    if (sumLen >= 120 && sumLen <= 600) readability += 25;
    else if (sumLen > 0) readability += 10;
    else recs.push("Ajoutez un résumé professionnel de 2 à 4 phrases en haut du CV.");
    const bulletExp = exp.filter(e => /[\n•]/.test(e.desc || "")).length;
    if (exp.length && bulletExp / exp.length > 0.5) readability += 15;
    else if (exp.length) recs.push("Décrivez vos expériences en puces courtes (une réalisation par ligne).");
    readability = clamp(readability);

    // --- Expérience ---
    let experience = 30 + Math.min(exp.length, 4) * 12;
    const quantified = exp.filter(e => /\d/.test(e.desc || "")).length;
    if (exp.length && quantified / exp.length >= 0.5) experience += 15;
    else if (exp.length) recs.push("Ajoutez des résultats chiffrés (%, montants, volumes) à vos expériences.");
    if (!exp.length) recs.push("Ajoutez au moins une expérience (ou un projet / stage).");
    experience = clamp(experience);

    // --- Compétences ---
    const skillsScore = clamp(35 + Math.min(skills.length, 8) * 8);
    if (skills.length < 5) recs.push("Listez 5 à 8 compétences clés au minimum.");

    // --- ATS (sections + mots-clés de l'offre) ---
    let ats = 45;
    if ((data.summary || "").trim()) ats += 8;
    if (exp.length) ats += 12;
    if (skills.length) ats += 12;
    if (edu.length) ats += 8;
    let kwHits = 0, kwTotal = 0, missing = [];
    if (jobText) {
      const words = [...new Set(jobText.match(/[a-zàâäéèêëîïôöùûüç]{4,}/g) || [])];
      const kws = words.filter(w => !STOP.has(w)).slice(0, 40);
      const hay = JSON.stringify(data).toLowerCase();
      kwTotal = kws.length;
      kws.forEach(w => { if (hay.includes(w)) kwHits++; else missing.push(w); });
      const ratio = kwTotal ? kwHits / kwTotal : 0;
      ats += Math.round(ratio * 15);
      if (ratio < 0.5) recs.push("Reprenez davantage les mots-clés de l'offre (ex : " + missing.slice(0, 5).join(", ") + ").");
    } else {
      recs.push("Collez une offre d'emploi pour mesurer la compatibilité des mots-clés (ATS).");
    }
    ats = clamp(ats);

    const global = clamp(ats * 0.3 + readability * 0.2 + experience * 0.2 + skillsScore * 0.15 + presentation * 0.15);

    return {
      scores: { ats, readability, experience, skills: skillsScore, presentation, global },
      recommendations: recs.slice(0, 6),
      keywords: { hits: kwHits, total: kwTotal, missing: missing.slice(0, 12) }
    };
  }

  // Analyse d'un CV collé en texte brut (pour l'analyseur ATS) -> data approximatif
  function parseText(t) {
    t = t || "";
    const email = (t.match(/[\w.+-]+@[\w-]+\.[\w.-]+/) || [""])[0];
    const phone = (t.match(/(\+?\d[\d ().\-]{7,}\d)/) || [""])[0].trim();
    const lines = t.split("\n").map(s => s.trim()).filter(Boolean);
    let name = "";
    for (const l of lines) { if (l.length <= 42 && !/[@\d]/.test(l) && /[A-Za-zÀ-ÿ]{2,}/.test(l)) { name = l; break; } }
    const lower = t.toLowerCase();
    const hasExp = /(exp[ée]rience|poste|entreprise|20\d\d)/.test(lower);
    const hasEdu = /(formation|dipl[ôo]me|licence|master|universit|bac)/.test(lower);
    const hasSkills = /(comp[ée]tences|skills|logiciels?)/.test(lower);
    return {
      fullName: name, title: "", email, phone, summary: t.slice(0, 400),
      experiences: hasExp ? [{ desc: t }] : [],
      education: hasEdu ? [{ degree: "détecté" }] : [],
      skills: hasSkills ? [{ name: "détecté" }, { name: "détecté" }, { name: "détecté" }, { name: "détecté" }, { name: "détecté" }] : [],
      languages: [], interests: []
    };
  }

  return { score, parseText };
})();
