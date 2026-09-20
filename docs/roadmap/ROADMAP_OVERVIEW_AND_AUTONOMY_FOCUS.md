# Roadmapoverzicht en autonomie-eerst focus

**Vastgelegd:** 17 september 2026. **Classificatie:** brongebonden analyse en focusnotitie, geen uitvoerbare backlog. **NO_BUMP.**

**Gerichte statusupdate, 20 september 2026.** De EP-route voor een
repositorygebonden autonoom Quality/Security-profiel en Missiongebonden
mergebevoegdheid is [geleverd, geïsoleerd live gekwalificeerd en voor
`pcvantol/forge` geïnstalleerd en geselecteerd](../operations/REPOSITORY_BOUND_AUTONOMOUS_ASSURANCE_COMPLETION.md).
De target staat klaar voor binding aan een later afzonderlijk goedgekeurde
Mission. De productie-Mission 3, haar clean-CENTRAL-voorbereiding en haar
historische acceptatie blijven onuitgevoerd respectievelijk ongewijzigd.
De bevroren tellingen en overige roadmapfamilies hieronder veranderen niet.

## Tijdelijke uitvoering met twee architectsessies — 18 september 2026

De eigenaar kiest vóór Forge-cutover voor twee onafhankelijke Codex-sporen.
De [tweesporenplanning](DUAL_LANE_DEVELOPMENT_V1.md) en
[machineleesbare lane-indeling](dual-lane-development-v1.json) rangschikken
alle onderstaande families zonder deze historische telling te wijzigen.
Initialiseer [LANE_1](lanes/LANE_1.md) en [LANE_2](lanes/LANE_2.md); daarna
selecteert “geef volgende prompt (1/2)” één ready subset na actuele controle
van beide gedeelde registraties. Geen vaste rondebarrière, dubbele repositorywriter
of automatische Mission-/resetstart. Zodra Forge een geschikte geautoriseerde
scope gekwalificeerd kan dragen, wordt de volgende aftrap een Forge-Mission.
Dit is een tijdelijke operatorwerkindeling, geen nieuwe product-DAG of scheduler.

Doel van de eigenaar: het hoogoverbeeld terug kunnen vinden en focus houden op zo snel mogelijk werkpakketten door Forge zelf laten plannen, via EP uitvoeren en opvolgen. Niet eerst het hele platform met de hand afbouwen voordat het eigen werk kan overnemen.

De criteriumgebonden hersteluitwerking staat in
[Mission completion v2](../architecture/criterion-completion-v2.md), met de
[begrensde installed update-route](../operations/FORGE_INSTALLED_UPDATE_RUNBOOK.md).
Dit is navigatie naar de owning contracten; het wijzigt geen roadmapstatus en
claimt geen release, activatie of geslaagde productie-Mission.

Deze pagina bewaart de eerdere roadmapanalyse in een repository-first vorm. De [gedateerde volledige ID-inventaris](inventory/2026-09-17.json) bevat alle 194 records, bronrevisies, statussen, telregels en samenvoegingen; de [formaat- en leesinstructie](inventory/README.md) verklaart de compacte representatie. De inhoudelijke productroadmaps en hun eigenaren blijven leidend. Dit document is geen nieuwe Mission, toestemming, releaseplan, scheduler of peer-statusautoriteit.

## Het hoogoverbeeld

| Product | Benoemde werkpakketrecords | Analytische rollup-eenheden | Mogelijke aftrapfamilies |
| --- | ---: | ---: | ---: |
| Engineering Platform | 41 | 40 | 9 |
| Workspace | 36 | 36 | 9 |
| Forge Platform | 19 | 16 | 4 |
| Forge | 91 | 66 | 12 |
| Gezamenlijke knopen, eenmaal geteld | 7 | 7 | Binnen de families verwerkt |
| **Totaal geselecteerde scope** | **194** | **165** | **34** |

**194** telt de unieke benoemde records in de geselecteerde uitgewerkte deelroadmaps. **165** volgt uit het expliciete analytische rollupmodel. **34** is een mogelijke bundeling in samenhangende capability-opdrachten, niet het minimale aantal Codex-prompts, niet een goedgekeurde Missionlijst en niet een garantie dat iedere familie in één sessie afkomt.

De telling is bevroren op deze bronrevisies, ook als de huidige `main` of installatie inmiddels verder is:

| Repository | Inventarisbron |
| --- | --- |
| `pcvantol/engineering-platform` | `1cd72ff83b2da4d3fb8bec840975db326589c049` |
| `pcvantol/workspace` | `5ecd418bc9cdc983791bf35c07457ffdb2ad1166` |
| `pcvantol/forge-platform` | `88b256b274fb20487b7c0cce05ccd5a58a4516f1` |
| `pcvantol/forge` | `b46aac196f64d018ae75f0d3492c841df9985ceb` |

Geen code-voor-code audit van resterend werk is uitgevoerd voor deze telling. Een roadmaplabel `PLANNED` kan gedeeltelijk al geleverd werk bevatten. De snapshot mag dus niet worden gelezen als: nog 165 dingen vanaf nul bouwen. Reconcileer vóór werkselectie alleen de relevante owning bron, uitvoering en artifact-/installed-evidence; heropen gesloten reparaties niet omdat een ouder overzicht nog een brede node noemt.

## Waar de omvang zit

| Product | Families en rollup-aantallen |
| --- | --- |
| EP | Subagent-efficiëntie/assurance 9; taak-/rol-/modelbeleid 7; execution envelope 3; HTTP-conformiteit 3; projectbootstrap 7; parallelle Actions 6; governed progression 1; policy/release 2; projecthygiëne 2. |
| Workspace | HTTP/API/CLI 6; distributie 5; gesprekken 4; sizing 2; projectloop/roadmapbeheer 6; projectbootstrap 6; progression 2; policy/release 2; hygiëne 3. |
| Forge Platform | Installer/clean-install/UX/release 13; progression 1; policy/release 1; hygiëne 1. |
| Forge | Console/hosting/data-administratie 8; HTTP/API/CLI 5; inner-loop CI 7; outer-loop CI 5; sizing 6; projectloop/roadmapbeheer 9; gesprekken 5; projectbootstrap 9; parallelle Actions 7; progression 1; policy/release 2; hygiëne 2. |

De zeven gedeelde nodes zijn `GP-DC`, `GP-Q`, `GP-X`, `POL-B`, `POL-Q`, `VR-Q` en `HY-Q`. Ze worden niet bij iedere deelnemende repository opnieuw aan het totaal toegevoegd. De JSON bewaart afzonderlijk deelname-aantallen; die zijn nadrukkelijk niet optelbaar als unieke scope.

### De 29 samenvoegingen zijn geen verdwenen werk

Bij Forge zijn de 9 `FC-*`, 9 `FCP-*` en 7 `FSH-*`-uitwerkingen in het telmodel opgenomen in de 8 primaire `FOC-*`-deliverynodes. De bronnen verbinden ze via `delivered_by`. Dat betekent niet dat de hele Console in acht kleine prompts past, noch dat Server-only delivery op de volledige Console moet wachten.

Bij EP is `SA-ROLE` uitgewerkt in zeven `RMP-*`-nodes en daarom niet nogmaals toegevoegd. Bij Forge Platform zijn `FP-EP-CI-6/7/Q` analytisch gebundeld met de `IUR-*`-uitwerking. Vooral daar bestaat geen bewezen één-op-één equivalentie: de rollup is een planningsconventie, geen wiskundig minimum aan uitvoeringen. Alle oorspronkelijke IDs en redenen blijven beschikbaar in de snapshot.

Testscenario's, bewijsvoorwaarden, dependency-only peerreferenties, historische Foundation/documentatieafsluitingen en herhaalde hoofdlabels zijn niet als extra werkpakketten geteld. Niet-gemergd resetwerk en toekomstige correcties zijn geen stille toevoeging aan de bevroren telling. Brede nog niet vergelijkbaar gedecomponeerde doelen, zoals algemene Agent-fleet, ruimer OS-/installatielifecyclebereik, Knowledge/learning en forecasting, vallen buiten dit numerieke totaal.

## Focus: het platform moet zijn eigen resterende werk zo vroeg mogelijk overnemen

De mislukte productie-MISSION-0003 blijft een ongewijzigde, niet-gehaalde
acceptatiepoging. Haar drie samenhangende blockers vormen één verticale
herstelassignment: Forge bindt iedere seriële Action aan actuele Repository
Truth, bewaart toekomstige plannerideeën als forecast zonder Action-authority
en materialiseert een evidence-afhankelijke opvolger pas na nieuwe
plannerbeslissing; EP bereidt de Managed workspace onder lease voor op de
exacte Action-SHA en projecteert een afgehandelde submission buiten de actieve
queue. De volgende productieacceptatie is een afzonderlijke opdracht met
nieuwe T0 en ongewijzigde C01–C20. Deze roadmapbeschrijving is geen
kwalificatie- of installed-PASS. Parallelle Actions, autonome volgende-Mission-
selectie en de volledige Server/Workspace blijven aparte toekomstige scope.

Onderstaande focus is de praktische interpretatie van het eigenaarsdoel en de bestaande roadmaplijnen. Het is **geen nieuwe harde DAG-volgorde** en verleent geen toestemming om werk te starten. Raadpleeg de owning DAG voor echte afhankelijkheden; de grootte of recentheid van een familie bepaalt niet automatisch de prioriteit.

| Focus | Eerstvolgende aantoonbare waarde | Bestaande route / grens |
| --- | --- | --- |
| Concrete preflightblokkade sluiten | Een veilige baseline voor de reeds afgesproken autonomietest. | Alleen de geselecteerde reset-/integriteitsonderhoudsslice wanneer die volgens actuele owning readback nog nodig is. Een eenmalige clean-state-testvoorbereiding is geen resetverplichting voor iedere toekomstige Mission. |
| Inner-Mission-autonomie bewijzen | Eén goedgekeurde Mission; Forge leidt inhoudelijke Actions af, verwerkt EP-resultaten en plant een echte opvolger zonder mens als berichtenbus. | Bestaande Mission-3-acceptatie blijft intact; [Implementation DAG](../architecture/FORGE_V1_IMPLEMENTATION_DAG.md) en [inner-loop CI](FORGE_INNER_LOOP_CI_V1.md). Geen nieuwe testcriteria of fictieve PASS in deze notitie. |
| Zelfstandig laten doorwerken | Geïnstalleerde service/API, veilige stop/herstart en duurzame voortgang zonder tijdelijke handmatige procesregie. | Server-only deel van `FSH-SERVICES`, passende `FH-*`-services/adapters; [runtime-evolutie](../architecture/runtime-evolution-roadmap.md). Niet wachten op de complete Console, relay of Workspace. |
| Onafhankelijke Actions versnellen | Meerdere repositorygebonden Actions binnen één Mission werkelijk overlappend uitvoeren, met correcte joins en afzonderlijke evidence. | [Parallelle Action-runtime](PARALLEL_ACTION_RUNTIME_V1.md), Forge `PA-F*` en EP `PA-E*`; capaciteit en leases blijven EP-owned. Geen wijziging van de eerste seriële proef. |
| Menselijke aftrappen verminderen | Resultaten naar context/roadmap terugbrengen en uitsluitend de juiste volgende geautoriseerde Mission starten. | [Projectloop](LIVE_PROJECT_ROADMAP_MANAGEMENT_V1.md), `PRM-F-*` plus passende [outer-loop CI](FORGE_OUTER_LOOP_CI_V1.md). Begin met handmatige vrijgave of een exact goedgekeurde werklijst; volledige delegatie is afzonderlijk. |

Parallelle Actions en de projectloop zijn twee verschillende vervolgverbeteringen. Een seriële goedgekeurde werklijst hoeft niet op volledige cross-repositoryparalleliteit te wachten; twee onafhankelijke Actions binnen één Mission hoeven niet op een complete outer loop te wachten. Deze focusnotitie kiest geen onderlinge harde startvolgorde en verandert geen bestaande producer-evidencegate.

**Overdrachtsmoment:** zodra een passende scope door de geïnstalleerde, gekwalificeerde Forge-route wordt ondersteund en de relevante proef is geaccepteerd, is het voorstel om het volgende geschikte werkpakket daar als Mission onder te brengen, in plaats van standaard weer een volledig handmatig Codex-traject te starten. Wacht niet op afronding van alle 34 families of alle 165 tel-eenheden. Ontbrekende kritieke productfuncties kunnen nog rechtstreeks als geautoriseerd engineeringwerk worden gebouwd; vermeld dan precies waarom de bestaande Forge-route dat werk nog niet veilig kan dragen.

Een gewijzigde Forge- of EP-bron mag daarbij niet ongemerkt de draaiende orchestrator vervangen. Artifactkwalificatie, release, veilige activatie en live bewijs blijven afzonderlijke owning stappen.

## Van tel-eenheid naar aftrap

Eén node is niet verplicht één prompt, één Mission of één subagent. Een aftrap kan een samenhangend resultaat omvatten met meerdere contract-, implementatie-, test- en kwalificatiestappen. Omgekeerd kan een grote familie meerdere begrensde Missions nodig hebben. Elke subagent of review krijgt niet automatisch een nieuwe volledige engineeringtransactie.

Een bruikbare aftrap benoemt het gewenste resultaat, exacte scope en authority, bron-/artifactvoorwaarden, vereiste bewijsvoering en stopgrenzen. Binnen die grens kan Forge zijn Actions afleiden en EP de uitvoering organiseren. Een vooraf uitgeschreven Actionlijst als vervanging van Forge-planning bewijst geen autonomie.

Minder menselijke aftrappen betekent niet minder engineeringwerk of minder validatie. Beoordeel voortgang daarom op bewezen autonome levering en verminderde noodzakelijke menselijke tussensturing, niet op een dalend aantal labels, grotere prompts of groen gekleurde documentatie.

## Wat niet automatisch vóór autonomie hoort

De volledige Workspace-UX, rijke Console, universele installer, algemene multi-host Agent-fleet, complete modeloptimalisatie en nieuwe-projectbootstrap zijn waardevolle productlijnen. Ze zijn geen algemene prerequisite voor doorontwikkeling van de al gekoppelde repositories. Alleen een concreet ontbrekende bevoegdheid, veiligheidsgrens of werkelijk benodigde producerfunctie mag een gerichte afhankelijkheid toevoegen.

Nieuwe reviewbevindingen blijven evidence-gebonden voorstellen, tenzij zij binnen het al goedgekeurde werk een echte acceptatieblokkade zijn. Een hoge aanbevelingsscore geeft geen recht om de goedgekeurde werklijst te wijzigen. `APPROVED_WORKLIST` voert alleen exact vrijgegeven werk uit; `DELEGATED_DEVELOPMENT` vereist afzonderlijke begrensde bevoegdheid. Deze notitie activeert geen van beide modi.

## Gebruik bij de volgende Architect-sessie

Lees dit overzicht voor oriëntatie en gebruik daarna [ARCHITECT_SESSION.md](../../ARCHITECT_SESSION.md) en de [canonieke roadmap](../../knowledge/bootstrap/10_ROADMAP.md) voor authority en actuele bewijsreconciliatie. Vraag bij een mogelijke voorganger: blokkeert het ontbreken van deze exacte capability het volgende autonome resultaat, of staat zij alleen onder een groot ouderprogramma?

Leg bij de volgende werkselectie kort vast: beoogd autonoom resultaat; exacte nog ontbrekende capability; owning bewijs van reeds geleverd werk; kleinste samenhangende scope; wat via Forge kan en waarom eventueel nog niet; echte menselijke beslissing. Begin niet telkens opnieuw aan de volledige inventaris of aan reeds gesloten reporting-/telemetriereparaties.

De snapshots blijven gedateerd. Een nieuwe telling krijgt nieuwe bronpins en expliciete toevoegingen, samenvoegingen en uitsluitingen; oude tellingen blijven herkenbaar historisch. Een bijgewerkte telling is geen automatische Missionallocatie, prioriteitswijziging of runtimegoedkeuring. Statuswijzigingen horen met bewijs in de owning roadmap en uitvoeringsadministratie, niet alleen in dit samenvattende document.

## Leveringsgrens van deze notitie

Opslag van de analyse en navigatie, uitsluitend documentatie. Geen runtimecode, schema, packageversie, workflow, beleid, credential, database, lopende uitvoering of Mission gewijzigd. Geen nieuwe live-audit of statusclaim over de vier installaties. De oorspronkelijke bronpins en beperkingen zijn behouden; de compacte JSON verandert geen recordbetekenis.
