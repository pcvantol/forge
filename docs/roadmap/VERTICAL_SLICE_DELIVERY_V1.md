# Verticale slices: één aftrap, volledige autonome oplevering

De geselecteerde seriële Mission-slice heeft een eigen
[MISSION-0017-opleverrecord](../operations/MISSION_0017_VERTICAL_RELEASE_INSTALLATION_COMPLETION.md).
Dat record sluit uitsluitend de daar beschreven product- en installatiegrens;
parallelle Actions, Server/Workspace-uitbreiding en de bredere autonomiebacklog
houden hun afzonderlijke roadmapstatus.

**Afspraak:** `VERTICAL_SLICE_DELIVERY_V1`, 18 september 2026. **Eigenaar:** opdrachtgever van de twee lanes. **Toepassing:** iedere geselecteerde uitvoeringsopdracht in LANE_1 en LANE_2, vóór en na overdracht aan Forge. **NO_BUMP voor deze documentatielevering.**

De eigenaar vraagt dat ieder uitvoerbaar roadmap-item een echte verticale implementatieslice is: niet één prompt voor code en daarna nieuwe prompts voor tests, refactoring, DoD, owner authorization, PR of merge. De [tweesporenplanning](DUAL_LANE_DEVELOPMENT_V1.md), [machineleesbare indeling](dual-lane-development-v1.json) en beide sessierouters gebruiken deze afspraak. Zij legt het expliciete eigenaarsmandaat voor de normale lifecycle vast; zij is geen nieuw runtimegrant, scheduler, automatische start van de hele backlog of wijziging van peer-productgovernance.

## 1. De eenheid is een werkend resultaat, niet een technische laag

**Eén uitgegeven assignment = één afgebakend, bruikbaar resultaat tot de volledige toepasselijke Definition of Done.** Dezelfde opdracht omvat uitwerking, implementatie, nodige tests, noodzakelijke refactoring, onafhankelijke reviews en correcties, exacte kandidaatkwalificatie, beschermde main-merge en de afgesproken delivery aan de echte consumer.

De 194 historische records, 165 analytische tel-eenheden en 34 families blijven bron-/scopeverwijzingen, geen verplichte promptgrenzen. Technische nodes zoals CONTRACT, STORAGE, HTTP, TEST of Q kunnen samen interne stappen van één verticale slice zijn. Het huidige verzoek maakt niet met terugwerkende kracht alle 165 nodes onafhankelijk uitvoerbare features en verandert hun owning DAG niet. De architect bundelt de benodigde node-subsets bij selectie, met expliciete dekking per node; gedeeltelijke dekking sluit niet de hele parentcapability.

Een grote capability wordt zo nodig **vóór uitgifte naar kleinere verticale resultaten** verdeeld. Elk resultaat heeft een echte eigen consumergrens, toepasselijke negatieve tests en een afgeronde delivery. Niet splitsen naar horizontale opleverfases als “backend nu, aansluiten/testen/mergen later”. Een library-/producerfunctie kan een verticale slice zijn wanneer haar echte afnemer het geleverde contract zelfstandig kan gebruiken en die grens aantoonbaar gekwalificeerd is; een ongebruikt stubje met alleen mocks is dat niet.

Een expliciet gevraagde ontwerp-, documentatie- of read-only assessmentopdracht kan haar eigen volledige DoD hebben, maar wordt als zodanig getypeerd. Een contractdocument toevoegen is geen voltooide implementatie. Gebruik geen contract-only opdracht als standaard fallback om een lane bezig te houden terwijl het gevraagde functionele resultaat nog geen uitvoerbaar pad heeft.

## 2. Minimale intake voor iedere verticale slice

De architect legt vóór uitgifte vast:

| Veld | Vereiste betekenis |
| --- | --- |
| `vertical_outcome` | Welke concrete gebruiker, operator of producer/consumer kan welk nieuw gedrag werkelijk benutten? |
| `source_node_coverage` | De bestaande owning nodes en exacte subsets die intern worden geleverd; geen fictieve nieuwe Mission-ID. |
| `scope_and_non_goals` | Repository-/effectgrens, relevante afhankelijkheden en wat expliciet niet wordt veranderd. |
| `actor_and_authority_binding` | Werkelijke opdrachtgever, dit lifecyclemandaat en de ondersteunde owner-/operatorroute; productgrants/assurancerecords blijven echte afzonderlijke bewijsobjecten. |
| `acceptance_criteria` | Functioneel, negatief/security, regressies, compatibiliteit/migratie en toepasbare kwaliteitsregels. |
| `entrypoint_and_consumer_boundary` | CLI, API, UI, library, installer of CI-gate waarmee het gedrag werkelijk wordt gebruikt; geen ongeautoriseerde peerfallback. |
| `delivery_targets` | Owning main en, waar toepasselijk, bestaande registry, exact artifact en geselecteerde installatie/omgeving. |
| `completion_requirements` | Alle toepasselijke DoD-onderdelen en hun vereiste readback; niet achteraf afgezwakt om groen te worden. |
| `not_applicable_with_reason` | Bijvoorbeeld geen UI voor een headless library, geen productie-installatie voor een expliciet CI-only resultaat; niet “tests volgen later”. |
| `repository_and_runtime_reservations` | Beide lane-afspraken, gedeelde resources en geplande veilige release-/activatievensters. |
| `in_scope_repair_limits` | Bestaande run-/repair-/tijd-/budgetgrenzen blijven gelden; een nieuwe sessie reset deze niet. |
| `resume_reference` | Duurzame assignment, bron/evidence en eigen veilige hervattingsinformatie voor dezelfde opdracht. |

Kies de kleinste **volledige** scope, niet het kleinste aantal gewijzigde bestanden. Nodige aansluiting, foutafhandeling, migratie en lokale refactoring worden vooraf meegerekend. Treft men tijdens implementatie een noodzakelijk aangrenzend defect binnen hetzelfde geautoriseerde functionele effect, dan wordt het daar opgelost en getest. Een wezenlijk ander productdoel of een nieuwe bevoegdheidsgrens wordt niet via het woord “refactoring” binnengesmokkeld.

## 3. Eén lifecycle tot Done

```text
Vrijgegeven verticale slice en bestaande eigenaarsmachtiging
→ actuele bron en gereserveerde resources controleren
→ passende implementatie + noodzakelijke aansluiting/refactoring
→ gerichte tests, regressies en toepasselijke integratie-/securitytests
→ onafhankelijke Quality/Security waar de productpolicy die vereist
→ review-/CI-bevindingen binnen scope oplossen en opnieuw kwalificeren
→ echte owner-authorizationstappen via de ondersteunde geautoriseerde route
→ PR aanmaken/bijwerken, checks volgen, beschermde merge naar main
→ vereiste finalization en resultaatreconciliatie
→ waar afgesproken: exacte artifacts bouwen/kwalificeren/publiceren/teruglezen
→ waar afgesproken: veilig installeren/activeren en installed readback
→ eigen veilige afsluiting, geschoonde handoff en bewijsgebonden roadmapstatus
→ Done
```

De stappen volgen de actuele owning deliveryregels; dit diagram verplaatst geen vereiste gate naar ná haar beschermde effect. De uitvoerder handelt normale branches, commits, PR-aanmaak, reviewrequests, CI-wachten, in-scope reparaties, geldige owner-gates en merges zelf af. Hij stopt niet bij “code klaar”, “tests nog toevoegen”, “PR mergeable”, “klaar voor DoD” of “mag ik mergen?”.

Bestaande regels mogen meerdere PR’s vereisen, bijvoorbeeld implementatie en finalization. Die zijn interne deliverystappen binnen dezelfde assignment, niet automatisch nieuwe menselijke aftrappen. Een exact-headwijziging vereist herkwalificatie, niet vanzelf nieuwe Business-/ownergoedkeuring voor dezelfde ongewijzigde scope. Werkelijke findings blijven zichtbaar; het herstellen ervan mag de audit niet wissen.

**Tests, noodzakelijke refactoring, toepasselijke assurance, merge en overeengekomen delivery zijn geen apart backlogwerk dat later de slice alsnog afmaakt.** Niet-blokkerende verbeterkansen buiten de gekozen scope mogen wél als evidence-gebonden voorstellen worden vastgelegd. Een eigen acceptatiedefect naar zo’n voorstel verplaatsen om de huidige slice Done te verklaren is verboden.

Geldt een gepubliceerde package of geïnstalleerde service als afgesproken consumergrens, dan horen build, exacte artifactkwalificatie, release, registryreadback, veilige activatie en installed bewijs bij dezelfde opdracht. “Merged, release volgt” is dan een tussenstand. Een puur bron-/library-/CI-resultaat mag eindigen op de vooraf gerechtvaardigde eigen grens; eis niet automatisch een nieuwe productie-installatie bij iedere documentatie-/testwijziging.

## 4. Expliciet eigenaarsmandaat, geen herhaalde routinevragen

De eigenaar delegeert binnen de **geselecteerde en aan de uitvoerder vrijgegeven verticale slice** de gewone engineering- en deliverystappen. Dit omvat de benodigde owner-authorizationhandelingen, PR-/merge requests, beschermd mergen en de in die opdracht verklaarde release-/installatiedoelen. De executor mag de beschikbare bevoegde eigenaar-/operatorroutes gebruiken en de bestaande toestemming aan het concrete onderwerp binden, zonder voor iedere fase opnieuw akkoord te vragen.

Het teruggeven van “volgende prompt” blijft selectie en reservering, niet op zichzelf het starten van de uitvoering. Het uitvoeren van de aldus vrijgegeven opdracht draagt het lifecyclemandaat; er is geen extra los “nu ook testen/mergen”-besluit nodig. Dit mandateert geen willekeurige volgende backlog-Mission. Behoud strengere expliciete stop-/effectgrenzen uit reeds lopende opdrachten; vergroot hun scope niet stilzwijgend met deze documentatie.

**Machtiging is niet hetzelfde als vervalste assurance.** Bewaar werkelijk actor/rol, scope, policy, doel, kandidaat/artifact en bewijs. Automatiseer een owner-gate alleen via een ondersteunde handeling met de echte toegangsrechten en toepasselijke delegation. Schrijf geen handmatig PASS-, approval- of grantrecord om een weigering te verhullen. De implementerende agent kan niet zelf als onafhankelijke reviewer optreden. Afzonderlijke Business/Architecturebesluiten en deliveryrollen worden niet tot één fictieve goedkeuring samengevoegd.

Is dezelfde eigenaarstoestemming al toepasselijk en geldig, gebruik die en maak geen dubbele menselijke gate. Is er een echt niet-delegeerbare externe goedkeuring, ontbrekend recht, ingetrokken toestemming of contract dat automatisering daadwerkelijk niet toestaat, benoem precies die resterende stap als `BLOCKED_EXTERNAL_GATE`. Verander geen branch protection, required checks, reviewers, securitypolicy of budgetgrens om haar te omzeilen. Maak geen nieuw autorisatieframework als excuus om normale ondersteunde owneracties niet uit te voeren.

Alleen materiële uitzonderingen vragen opnieuw een besluit: ander productdoel of repositoryeffect buiten de vrijgegeven scope; nieuwe irreversibele productiedatamutatie/reset; privilege-/credentialwijziging; nieuwe publieke verspreiding van vertrouwelijke gegevens; niet eerder toegestane kosten/target; of de werkelijke niet-delegeerbare externe gate. Normale implementatie, benodigde tests/refactoring, reviewfixes, kwalificatie, PR, main-merge en verklaarde delivery zijn **geen** zulke uitzonderingen.

Bestaande publicatiecontrole blijft vóór de eerste push: echte hostpaden, runtime/consumeridentiteiten, lokale receipts/digests en secrets blijven lokaal; publieke documentatie gebruikt de geschoonde vorm. Deze afspraak autoriseert geen history rewrite, protection-bypass, nieuwe credential, productie-CENTRAL-reset of Mission-3-start. Parkeringen en testcriteria, inclusief Mission 3’s no-retry-eis, blijven intact. Normale ontwikkeliteraties van andere slices blijven binnen hun eigen bestaande grenzen toegestaan.

## 5. Twee lanes blijven verantwoordelijk tot de beloofde grens

Eén assignment blijft gedurende implementatie, review, release en de gevraagde activatie dezelfde assignment. `REVIEW`, `WAITING_DEPENDENCY`, `BLOCKED_EXTERNAL_GATE`, `WAITING_RELEASE` en `WAITING_ACTIVATION` zijn zichtbare tussenstanden, niet Done of een vrijbrief voor een tweede concurrerende writer. Behoud de bestaande lane-state-enums; registreer nadere lifecyclefase/redencode afzonderlijk wanneer er geen passende state bestaat.

De executor laat intern opvolgstappen, subagents en reviewers werken waar hun scopes veilig geïsoleerd zijn; dat maakt hen geen extra lane of eigenaar van andermans repository. Deelresultaten/contracten mogen na beschermde levering een andere lane ontsluiten. Daarmee kan producer/consumerwerk overlappen zonder de hele slice of familie voortijdig gesloten te verklaren.

Voor een cross-productresultaat leggen beide lanes vóór uitgifte hun grenzen en gezamenlijke contract/evidencejoin vast. Elke eigenaar levert zijn deel compleet met eigen tests, review en protected merge. De gezamenlijke operationele claim wacht op werkelijke integratiekwalificatie; die wordt onder de vooraf aangewezen nog open assignment uitgevoerd, niet als verrassende derde “maak het af”-prompt. Een zelfstandig gekwalificeerde producerlevering is apart rapporteerbaar, maar bewijst geen niet-geteste volledige productketen.

Gedeelde activatie- en live-testvensters worden tussen de lane-registraties gecoördineerd zonder de gebruiker als berichtenbus. Wachten op zo’n venster maakt een bronlevering niet ongedaan; wel blijft de beloofde installed finish line open. Normale hoofdbranch- of runtimeactivatie in de andere lane mag de lopende Mission-3-baseline niet wijzigen.

Een sessie-/contextlimiet maakt een beknopte duurzame continuation nodig, geen nieuwe opdrachtidentiteit, scope, repairbudget of extra roadmap-item. Het eerlijke tussenoordeel is onvoltooid met dezelfde hervattingsreferentie. Waar de omgeving geen hervatting zonder mens ondersteunt, benoem dat concreet; beloof geen achtergrondwerk of magische sessiecontinuïteit. Ook dan blijft “voeg tests/merge toe” geen nieuw functioneel werkpakket.

## 6. Concrete hersnijding van technische roadmapnodes

Onderstaande voorbeelden zijn selectieregels, geen nu uitgegeven opdrachten en geen vrijstelling van owning afhankelijkheden.

| Geen bruikbare implementation-aftrap | Wel een verticale aftrap |
| --- | --- |
| “Maak WH-CONTRACT; daarna services; later tests en merge.” | “Lever één werkelijk bruikbare Workspace read-only project/status-operatie via de eigen service en gekozen ingang, inclusief contract, fout/authorizationgevallen, tests, docs en protected delivery.” |
| “Voeg PA-F0-schema toe en sluit het item.” | “Lever een bruikbare gevalideerde multi-Action-planning/readback-slice met de benodigde contract-/opslag-/ingangsdelen, negatieve tests en beschermd geleverd producerbewijs; claim nog geen parallelle EP-uitvoering.” |
| “Implementeer twee EP-workers; herstel isolatie en bewijs later.” | “Lever begrensde onafhankelijke uitvoering op twee toegestane repositorytargets inclusief admission, isolatie, capaciteit, failure-/restartgevallen en volledige scope-evidence; producercontract is een echte vooraf vereiste input.” |
| “Bouw de server; maak er later een werkende installatie van.” | “Lever de gekozen standalone serve/API-slice tot de afgesproken geïnstalleerde grens, inclusief statebehoud, veilige stop/herstart, tests, reviews, release/activatie en readback.” |
| “Installeer de fix; schrijf daarna een nieuwe prompt om DoD te halen.” | “Repareer de bedoelde onderhoudsovergang met volledige echte CLI/coördinatorregressie, gekwalificeerde artifacts, veilige update en geschoonde completion record; geen niet-geautoriseerde live reset.” |

Een complete familykwalificatie kan later meerdere zelfstandig afgeronde slices combineren. Dat is een expliciet productdoel, geen excuus om de vereiste regressies of integratie van de huidige slice uit te stellen. Bewaar de oorspronkelijke technische nodes als traceerbaarheid; ga niet alle 165 records opnieuw nummeren of tellen.

## 7. Verplicht blok in iedere volgende uitvoeringsprompt

```text
VERTICAL_SLICE_DELIVERY = V1
Eén assignment, één volledig verticaal resultaat tot de verklaarde DoD.
De opdrachtgever autoriseert de normale lifecycle binnen deze vrijgegeven
scope: implementatie, noodzakelijke refactoring, tests, reviewcorrecties,
echte owner-authorizationstappen via ondersteunde routes, PR, protected merge,
finalization en de expliciet verklaarde release-/installatiedelivery.
Vraag voor die routinehandelingen geen hernieuwd algemeen akkoord.

Definieer vóór implementatie de concrete consumergrens, acceptatie,
node-subset, targets, bewijs en scopebeperkingen. Lever alles binnen dezelfde
assignment. Stop niet bij code klaar, tests later, PR mergeable of mag ik mergen.
Een nieuwe kandidaat wordt opnieuw gekwalificeerd; geen valse reviews/grants,
geen bypass van protections en geen overschrijding van bestaande repairlimieten.

Noodzakelijke in-scope correcties voer je zelf uit. Alleen een materiële
scope-/authoritywijziging of echte externe niet-delegeerbare blokkade vraagt
een besluit. Een sessiehervatting behoudt dezelfde assignment en criteria.
Done vereist alle toepasselijke bron-, review-, merge- en verklaarde artifact/
installed-readbacks. Houd private infrastructuurgegevens buiten publieke Git.
Start na afronding niet zelfstandig een nieuwe roadmapopdracht of Mission.
```

Dit blok wordt aangevuld met concrete scope en DoD, niet als vrijblijvende appendix naast een horizontale opdracht gezet. De architect verwerpt een prompt waarvan het beloofde resultaat alleen werkend wordt na een nieuwe test-/integratie-/mergeopdracht. Zowel DIRECT_CODEX als een latere FORGE_MISSION_KICKOFF erft deze afleververwachting; Forge blijft zijn eigen Actions plannen en de owning runtime blijft echte bevoegdheden verifiëren.

## 8. Sluiting en controle van de afspraak

Rapporteer per assignment: het behaalde verticale resultaat; bron-/node-dekking; tests en onafhankelijke assurance; alle owning PR’s en mergecommits; benodigde artifact/release-/installed-evidence; gebruikte owner-authorizationroute; open materiële beperkingen; en de veilige geschoonde handoff. Verplichte nog niet uitgevoerde DoD staat als open, nooit als groen of vrijblijvende follow-up.

Controleer de planning-/promptstructuur op: alle 34 families erven deze afspraak; geen dubbele of verloren node-ID; geen contract/test/merge-fase als zelfstandige implementatieaftrap; intake bevat consumergrens en DoD; geldige routine-owneracties vragen geen extra bevestiging; echte externe gate en scopewijziging blijven herkenbaar; geen impliciete live reset of nieuwe Mission; geen gewijzigde lane-reserveringen door deze documentatiewijziging.

Dit is een aangescherpte operator- en promptafspraak, geen bewijs dat de huidige Forge/EP-runtime deze volledige workflow al autonoom ondersteunt. Deze wijziging zelf is een complete documentatieslice met protected merge en links vanuit de bestaande routers; geen productrelease of installatie nodig. De latere echte uitvoering moet haar eigen resultaat bewijzen.
