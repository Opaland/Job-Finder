// Smoke test navigateur : les 8 onglets de l'interface se chargent sans erreur JS.
// Prérequis : backend lancé sur :8000 (avec frontend/dist buildé) et Playwright
// installé à la racine du dépôt : npm i -D playwright && npx playwright install chromium
// (PW_MODULE=/chemin/vers/playwright si tu l'as installé ailleurs).
// Usage : node scripts/smoke_ui.mjs [url]   (défaut http://127.0.0.1:8000/)
let chromium
try {
  ({ chromium } = await import(process.env.PW_MODULE || 'playwright'))
} catch {
  console.error(
    "Playwright n'est pas installé : lance « npm i -D playwright && npx playwright install chromium »\n" +
    'à la racine du dépôt, ou indique le module avec PW_MODULE=/chemin/vers/playwright.',
  )
  process.exit(1)
}

const url = process.argv[2] || 'http://127.0.0.1:8000/'
const launch = process.env.PW_CHROMIUM ? { executablePath: process.env.PW_CHROMIUM } : {}
const browser = await chromium.launch(launch)
const page = await browser.newPage()
const erreurs = []
page.on('pageerror', (e) => erreurs.push(`pageerror: ${e.message}`))
page.on('console', (m) => { if (m.type() === 'error') erreurs.push(`console: ${m.text()}`) })

const onglets = [
  ['Tableau de bord', 'h1:has-text("Tableau de bord")'],
  ['Offres', 'h1:has-text("Offres")'],
  ['Kanban', '.kcol'],
  ['Statistiques', 'h1:has-text("Statistiques")'],
  ['Marché', 'h1:has-text("Marché")'],
  ['Journal', 'h1:has-text("Journal")'],
  ['Profil & CV', 'h1:has-text("Profil")'],
  ['Sources & réglages', 'h1:has-text("Sources")'],
]

let echec = false
try {
  await page.goto(url, { waitUntil: 'domcontentloaded' })
  for (const [libelle, attendu] of onglets) {
    // Cibler le bouton de navigation (App.jsx) : « text=Offres » attraperait
    // aussi « Nouvelles offres », « Voir toutes les offres → », etc.
    if (libelle !== 'Tableau de bord') {
      await page.click(`button.nav:has-text("${libelle}")`)
    }
    await page.waitForSelector(attendu, { timeout: 15000 })
    console.log(`✔ ${libelle}`)
  }
} catch (e) {
  echec = true
  console.error(`✘ Échec : ${e.message}`)
}

if (erreurs.length) {
  echec = true
  console.error('Erreurs JS relevées :\n' + erreurs.join('\n'))
} else {
  console.log('Aucune erreur JS.')
}
await browser.close()
process.exit(echec ? 1 : 0)
