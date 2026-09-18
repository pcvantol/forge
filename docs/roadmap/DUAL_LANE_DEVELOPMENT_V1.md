# Twee ontwikkelsporen tot Forge het werk overneemt

**Vastgelegd:** 18 september 2026. **Status:** owner-requested tijdelijke werkindeling met expliciet begrensd lifecyclemandaat; geen nieuwe productruntime, automatische Missionlijst of runtimegrant. **NO_BUMP.**

Doel: maximaal twee onafhankelijke Codex-uitvoeringsopdrachten tegelijk, vanuit twee blijvende architectsessies. `ARCHITECT_1` bedient `LANE_1`; `ARCHITECT_2` bedient `LANE_2`. Na eenmalige initialisatie volstaan **“geef volgende prompt (1)”** en **“geef volgende prompt (2)”**. Het doel blijft zo vroeg mogelijk geschikte werkpakketten door Forge laten afleiden en via EP uitvoeren.

**Iedere uitgegeven opdracht is voortaan een volledige verticale slice volgens [VERTICAL_SLICE_DELIVERY_V1](VERTICAL_SLICE_DELIVERY_V1.md).** Implementatie, noodzakelijke refactoring, tests, reviewcorrecties, echte owner-authorizationhandelingen, PR, protected main-merge en verklaarde release/installatie zijn interne stappen van dezelfde aftrap. Geen tweede of derde prompt om de oorspronkelijke DoD alsnog te halen. Het expliciete eigenaarsmandaat dekt normale lifecyclehandelingen binnen de geselecteerde vrijgegeven scope; echte productrechten, onafhankelijke assurance en materiële scopegrenzen blijven gelden.

De indeling ordent de bestaande [inventaris en focus](ROADMAP_OVERVIEW_AND_AUTONOMY_FOCUS.md), maar verandert geen harde afhankelijkheden, peer-eigenaarschap, parkeringen of Mission-3-criteria. De [machineleesbare indeling](dual-lane-development-v1.json) verwijst naar alle 165 analytische tel-eenheden uit de 34 families, met zeven gezamenlijke nodes eenmaal. De snapshot van 17 september blijft ongewijzigd. Technische nodes zijn scope-/bewijsreferenties, niet automatisch uitvoerbare verticale items of één prompt per node.

## 1. Twee rollende rijen, geen verplichte gezamenlijke rondes

| Sessierouter | Primair werk | Onafhankelijke terugval | Gedeelde registratie |
| --- | --- | --- | --- |
| [LANE_1](lanes/LANE_1.md) | Forge: autonomie, zelfstandige services, planning en projectloop | Forge Platform: zelfstandige bruikbare compositie-/beheerfunctie tot eigen DoD | [Forge #141](https://github.com/pcvantol/forge/issues/141) |
| [LANE_2](lanes/LANE_2.md) | EP: correcte/efficiënte uitvoering en parallelle Actions | Workspace: bruikbare eigen service/read-only operatie inclusief ingang en tests; consumers zodra qualified | [Forge #142](https://github.com/pcvantol/forge/issues/142) |

Dit zijn standaard repositoryhouders, geen permanente productteams. De pools overlappen niet zodat gelijktijdige NEXT-aanvragen niet dezelfde repository claimen. Zonder bevestigde overdracht schrijft lane 1 niet in EP/Workspace en lane 2 niet in Forge/Forge Platform. Vrije keuze binnen de eigen pool blijft mogelijk. Een andere verdeling, zoals Workspace in lane 1 en EP in lane 2, volgt de korte tweezijdige overdracht hieronder.

Een lane die klaar is, hoeft niet op de andere te wachten. Zij kiest de hoogst relevante werkelijk uitvoerbare **verticale** subset. Een geblokkeerde dependency wordt niet omzeild. Wanneer geen veilige geautoriseerde combinatie bestaat, is `WAIT` correct. “Altijd twee” is een benuttingsdoel, geen reden voor kunstmatige contract-only drukte, scopegroei of resourceoverbelasting. De telling is geen mathematisch optimale tijdsverdeling.

## 2. Voorkeursvolgorde in bruikbare resultaten

De tabel is selectieoriëntatie, geen execution-DAG, starttoestemming of één opdracht per opgesomde technische node. Bundel per aftrap alle lagen en toepasselijke DoD voor haar concrete consumergrens. Een producercontract mag intern eerder worden geleverd om de andere lane te ontsluiten; de oorspronkelijke slice blijft open tot haar afgesproken finish line.

| Moment / prioriteit | LANE_1 | LANE_2 | Onafhankelijkheid en volledige slicegrens |
| --- | --- | --- | --- |
| Huidige voorbereiding | Bestaande reset-`prepare → revalidate`-correctie adopteren en volledig tot de reeds afgesproken qualified/installed grens afronden, indien nog open | Als EP bezet is: een zelfstandig bruikbare Workspace eigen read-only service/ingang met contract, authorizationgevallen, tests en protected delivery; anders een volledige ontbrekende EP-context/isolationverbetering | Geen tweede resetopdracht, geen losse WH-CONTRACT-aftrap zonder implementatie. Bestaande bron-/runtimereserveringen eerst vaststellen. |
| Clean-preflight en Mission 3 | Alleen het bestaande expliciet geautoriseerde testcontract, inclusief zijn volledige preflight en bewijs | Onafhankelijke Workspace-operatie op geïsoleerde fixtures tot eigen DoD, zonder canarytarget of actieve Forge/EP te wijzigen | Beide lanes respecteren de freeze; deze tabel verleent geen resetautorisatie en wijzigt geen acceptatiecriteria. |
| Na beoordeling live proef | Bruikbare standalone Forge serve/API-slice met benodigde FSH/FH/FCI-delen, tests, veilige herstart, protected delivery en afgesproken installed bewijs | Eén complete EP-correctheids/efficiëntieverbetering door het werkelijke providerpad met regressies, review, merge en toepasselijke consumentdelivery | Gescheiden bron/fixtures; activatie in overeengekomen venster. Geen “server nu, installatie later”-verrassing of verplicht wachten op hele Console/SA-familie. |
| Paralleliteit voorbereiden | Bruikbare multi-Actionplanning/readback-slice, met benodigde `PA-F0/F1/F2`-delen intern, negatieve tests en exact geleverd producercontract | Na werkelijk beschikbaar Forge-contract: complete begrensde EP-concurrencyslice over vereiste `PA-E*`-delen, inclusief isolatie, foutpaden en eigen bewijs | Afhankelijkheidsvolgorde blijft. Contractvrijgave kan intern overlappen met vervolgwerk; geen mock-PASS voor live peeruitvoering. |
| Paralleliteit aansluiten | Complete Forge-consumeraansluiting tot afgesproken geverifieerde parallelle keten via `PA-F3/F4/F5/FQ`-subsets | Benodigde EP producer-/bewijsaanvulling tot eigen volledige kwalificatie en delivery | Leg vooraf vast wie de gezamenlijke join uitvoert onder zijn open assignment. Geen onverwachte derde prompt voor integratietests of merges. |
| Werkvoorraad zonder eigenaar als berichtenbus | Bruikbare manual/approved-worklist-slice met nodige `PRM-F-*`- en `FCO-*`-delen, echte gates, tests en oplevering | Complete benodigde EP policy/progression/receiptfunctie of zelfstandige Workspace read-only beslisprojectie | Geen afhankelijkheid van de gehele delegatie-/paralleliteitsfamilie; oorspronkelijke PRM/FCI/FCO-evidence blijft leidend. |
| Overdrachtsmoment | Volgende ondersteunde verticale scope als Forge-Missionaftrap met dezelfde DoD | Hetzelfde per scope; DIRECT_CODEX alleen met concrete ontbrekende productcapability als reden | Niet wachten op alle 34 families; twee Codex-lanes autoriseren geen nog niet ondersteunde parallelle product-Missions. |

Canonieke navigatie: [runtime-evolutie](../architecture/runtime-evolution-roadmap.md), [inner-loop CI](FORGE_INNER_LOOP_CI_V1.md), [Forge-paralleliteit](PARALLEL_ACTION_RUNTIME_V1.md), [EP-paralleliteit](https://github.com/pcvantol/engineering-platform/blob/main/docs/development/PARALLEL_ACTION_EXECUTION_V1_DAG.json), [projectloop](LIVE_PROJECT_ROADMAP_MANAGEMENT_V1.md), [EP-efficiëntie](https://github.com/pcvantol/engineering-platform/blob/main/docs/development/SUBAGENT_ORCHESTRATION_V1_ROADMAP.md) en [Workspace-HTTP](https://github.com/pcvantol/workspace/blob/main/docs/WORKSPACE_HTTP_API_V1_DAG.json). Ververs vóór selectie de relevante eigenaar en vereiste evidence; een navigatielink is geen bewijs van implementatie.

**Bestaand werk adopteren:** Forge #140 beschrijft een vóór reset-apply afgebroken voorbereiding, geen gestarte Mission. Daarna is een herstelprompt uitgegeven. Stel eerst vast of die loopt of klaar is en behoud haar assignment/scope. De oorspronkelijke reset-/release-/installatieleveringen en EP #271/#272 niet opnieuw openen door een oude PLANNED-telling. Strengere reeds gegeven instructies, zoals geen live reset, blijven gelden.

## 3. Familie, technische node en verticale aftrap blijven onderscheiden

Alle twaalf Forge- en vier Forge Platform-families liggen standaard bij lane 1 (82 eigen rollup-eenheden); de negen EP- en negen Workspace-families bij lane 2 (76). Zeven gedeelde nodes blijven gezamenlijke bewijsjoins, eenmaal geteld, met lane 1 als communicatiecoördinator en code bij de echte repositoryhouder. 82/76 is geen uren-/tokenverdeling.

Elke familie erft de [verticale afleverafspraak](VERTICAL_SLICE_DELIVERY_V1.md). De oude nodes en dependencies blijven intact als interne traceerbaarheid. Verklein een te grote aftrap langs bruikbare verticale resultaten, niet langs contract/code/tests/merge. Een zelfstandig vereist ontwerprapport wordt expliciet DESIGN_ONLY geselecteerd en als ontwerp gesloten, nooit als implementatie-PASS.

Grote restfamilies — volledige Console, rijk modelbeleid, gesprekken, universele installer en nieuwe-projectbootstrap — vormen reservehorizon of toekomstige Forge-werklijst, niet een verplicht direct-Codexprogramma. Ze komen alleen in beeld bij aantoonbare bijdrage of onafhankelijk nuttig resultaat zonder de primaire lijn te vertragen. De 29 historisch samengevoegde records blijven in de inventaris; een complete Server-only slice kan relevante `FSH-SERVICES`-delen benutten zonder heel `FOC-*` af te maken. Carry-overonderhoud en Mission 3 worden niet stil als extra inventarisnodes geteld.

## 4. Wat “geef volgende prompt (1/2)” doet

Lees actuele main van de lane-afspraken, [deliverycontract](VERTICAL_SLICE_DELIVERY_V1.md), JSON, beide issues, relevante PR’s/branches en de eigen vorige assignment. Gebruik werkelijke lokale readback wanneer nodig en beschikbaar. Geen open PR is geen bewijs van afwezige lokale writers. Een nieuwe sessie heeft geen gedeeld chatgeheugen als statusautoriteit.

1. **Reconcileer de vorige aftrap.** Bij ISSUED/RUNNING/REVIEW of onzekere effecten geen tweede opdracht. Geef dezelfde assignment/status of benodigde continuation. Merge alleen sluit geen nog vereiste tests, finalization, release, installatie of evidence. Bij BLOCKED blijft de resource bezet tot expliciet bewezen veilige pauze.
2. **Toets cutoff.** Gebruik de geautoriseerde gekwalificeerde Forge-route zodra zij de scope kan dragen. Geen vooraf geschreven Actionlijst als vervanging van Forge-planning. Motiveer een DIRECT_CODEX-uitzondering concreet.
3. **Selecteer één ready verticale slice.** Prioriteit: echte autonomieblokkade, producerwerk dat de andere lane ontsluit, relevant ready primair werk, veilige fallback. Toets owning predecessors, parkeringen en rechten. Bind resultaat, concrete consumergrens en volledige toepasselijke DoD; een technische node alleen is geen aftrap.
4. **Bind lifecyclemandaat en resources.** Neem de bestaande expliciete eigenaarstoestemming voor implementatie, tests/refactoring, reviewfixes, ondersteunde owneracties, PR/merge en verklaarde delivery op. Definieer targets en uitzonderingen. Geen routinematige herbevestiging, geen nieuwe externe rechten verzinnen. Respecteer repo-/runtime-/test-/release-/canaryreserveringen.
5. **Schrijf en lees de eigen registratie terug.** Verhoog revision, behoud geschiedenis, noteer assignment, bron/nodes, DoD, authority, dependencies, targets en evidence. De peer mag niet conflicteren. Issue-revision is geen atomische GitHub-lease; de hieronder beschreven schrijfafspraken blijven vereist.
6. **Geef één complete uitvoeringsprompt.** Gebruik het verplichte deliveryblok uit het gekoppelde contract. Promptuitgifte is geen uitvoering; na vrijgave handelt de executor de hele lifecycle zelf af. Geen extra opdracht “nu tests”, “haal DoD”, “mag ik mergen” of “maak release af”. Geen automatische nieuwe backlogopdracht na Done.

Ontbreekt de gedeelde lees-/schrijfroute, claim geen reservering. Geef de concrete beperking, niet een verzonnen assignment of omweg langs productgovernance. De directe eigenaarstoestemming is geen vervanging van niet-beschikbare technische toegangsrechten.

## 5. Gedeelde registratie zonder derde scheduler

Issues #141/#142 zijn lichte aftrap-/handoffregistraties, geen atomische database, distributed lock of vervanging van EP-leases. Precies één architectschrijver per lane en disjuncte repositoryhouders voorkomen normale selectieraces; echte product-/repositorylocks blijven nodig. Een overgedragen architectsessie vereist dat de oude is gestopt; stilte of timeout geeft geen resource vrij.

De architect schrijft de eigen assignmentregistratie. De executor schrijft voortgang en geschoonde resultaten via de gekoppelde PR/handoff en wacht niet op de architect om normale review-/mergehandelingen uit te voeren. Hij kent zichzelf geen volgende roadmapopdracht toe. De architect verwerkt bewijs bij de volgende NEXT, of behoudt dezelfde assignment zolang de DoD niet sluit. Private lokale evidence wordt alleen via veilige referentie/attestatie weergegeven, niet als publiek onafhankelijk herhaalbare live-audit.

Minimum per assignment:

```text
lane / registration_revision / assignment_id / plan_revision
state: ISSUED | RUNNING | REVIEW | WAITING_DEPENDENCY | BLOCKED |
       PAUSED_SAFE | COMPLETED | CANCELLED_SAFE | TRANSFERRED_TO_FORGE
lifecycle_phase / blocking_reason / resume_reference
vertical_outcome / source_node_coverage / source_pins / unchanged_acceptance
entrypoint_and_consumer_boundary / scope_and_non_goals
actor_and_authority_binding / in_scope_repair_limits
completion_requirements / not_applicable_with_reason / expected_evidence
delivery_targets / repository_and_runtime_reservations
execution_mode: DIRECT_CODEX | FORGE_MISSION_KICKOFF
dependency_evidence / owning_PRs / candidate_SHA / merge_SHA
public_artifact_evidence / installed_or_live_evidence_when_required
remaining_effects_or_locks / sanitized_result_reference
```

De oorspronkelijke registers begonnen `UNASSIGNED_NEEDS_RECONCILIATION`; dat bewijst geen lokale leegte. Oude evidence/uitgiftes worden niet verwijderd. Een gesloten issue of groene checkbox is geen productacceptatie. Geen COMPLETED zolang vereiste test-, review-, merge-, release- of installed evidence ontbreekt. Beide lanes schrijven hun eigen issue zonder de globale planningsbestanden of de andere registratie te muteren. Dit deliveryaddendum stelt op zichzelf geen actieve assignment vast.

### Repository tijdelijk overdragen

Binnen bestaande scope mag overdracht zonder eigenaar als berichtenbus. Requester registreert transfer-ID, nieuwe epoch, repo en begrensde scope. Huidige houder bevestigt PAUSED_FOR_TRANSFER en dat geen executor, open aftrap, auto-merge of runtime-effect die scope kan wijzigen; daarna geeft hij exact die overdracht vrij. Ontvanger leest terug en bevestigt dezelfde transfer/epoch vóór uitgifte. De oude houder start vanaf vrijgave niets meer op die repo, ook bij onzekere ontvangst.

Teruggave is omgekeerd: bewezen quiescence en RELEASE, gevolgd door bevestiging van terugname. Geen timeout of lege PR-lijst als automatische vrijgave. Conflicterende epochs blokkeren beide selecties. Materiële nieuwe scope/effects vereisen passende authority. Issues zijn agent-gevolgde coördinatie, geen geleverd automatisch lockprotocol.

Cross-productwerk kan twee complementaire **complete owning slices** zijn met vooraf afgesproken contract en integratiejoin. De verantwoordelijke open assignment sluit het integratiebewijs; niet later een verrassende derde aftrap voor tests of merge. Wanneer bestaand herstel beide pools al reserveert, adopteer die opdracht in plaats van dubbel implementeren; de andere lane kiest een vrije onafhankelijke repository of wacht. Geen derde writer via subagents.

## 6. Bronparalleliteit is niet installatieparalleliteit

Losse worktrees zijn niet voldoende voor veilige parallelle writers in één repository. Totdat de relevante productcapability gekwalificeerd is: één muterende assignment per canonieke repository. Niet andermans featurebranch, main, stash, cleanup of dagelijkse checkout gebruiken.

Scheid fixtures, databases, poorten en scratch. Deel een signingrunner, schaarse lokale resource of publicatierechten alleen onder passende reservering. Eén eigenaar reserveert productreleaseversie en artifactpublicatie. Een fallbackprompt installeert niet ongemerkt andere producten of wijzigt credentials.

**Live reset/E2E-venster:** beide registers leggen hetzelfde expliciete venster vast. Uitvoerende lane reserveert canarytarget-main, gebruikte installaties en echte gedeelde resources; peer bevestigt geen conflicterende effecten. Onafhankelijke Workspace/Platformbron op fixtures mag doorgaan. Geen canarytarget-merge, artifactactivatie, restart, reset, peerconfigwijziging of gedeelde datamutatie tijdens T0 tot terminale reconciliatie. EP-bronontwikkeling mag alleen bij expliciet bewezen scheiding van alle proefresources en zonder activatie. Een gemeten failure blijft zichtbaar mislukt; de andere lane poetst die niet weg.

Release-/installatievensters worden eveneens tweezijdig geregeld waar runtimes gedeeld zijn. Wachten op een veilig venster is een fase van dezelfde assignment, geen extra prompt of voortijdige Done. Bronwerk dat werkelijk onafhankelijk is kan onder de bestaande veilige pauze-/reserveringsregels doorgaan. Bestaande externe gates en productbeperkingen worden niet uitgeschakeld door het lifecyclemandaat.

## 7. Outputcontract van iedere gegenereerde prompt

Begin met lane, assignment-ID, issue, planrevisie, productrepo, verticale uitkomst, bronpin en exacte node-subset. Voeg het verplichte [verticale deliveryblok](VERTICAL_SLICE_DELIVERY_V1.md#7-verplicht-blok-in-iedere-volgende-uitvoeringsprompt) toe, plus concrete DoD, ingang/consumergrens, targets, effectbeperkingen, herstelbudget en resources.

De executor bezit de hele normale uitvoering: implementatie, nodige tests/refactoring, reviews, in-scope fixes, ondersteunde owner-authorizationhandelingen, PR, protected merge, finalization en gevraagde artifact/installed oplevering. Geen routinematige terugvraag voor wat de eigenaar al heeft gemandateerd. Wel een concrete blokkade bij niet-delegeerbare externe approval, ingetrokken recht of materiële nieuwe scope; geen fabricage van menselijke/independent-reviewevidence.

Respecteer eigen projectregels, peer-HTTPgrenzen en ander werk. Een bestaand finding-ID wordt met bewijs gesloten; een buiten-scope kans wordt een voorstel, niet nieuw verplicht werk. Een eigen DoD-defect mag niet naar dat voorstel worden weggeschreven. Publieke PR/handoff en roadmapstatus onderscheiden bron, kwalificatie, artifact, activatie en acceptatie.

Saniteer vóór eerste commit/push: alleen publieke bron-/artifactreferenties en expliciete aliases. Geen echte lokale paden, host/runtime/consumeridentiteiten, Keychainrefs, lokale plan/backup/databasedigests of secrets. Volledige operationele evidence blijft afgeschermd lokaal. Geen historyrewrite of ongeautoriseerde cleanup van de eerder blootgestelde branch.

## 8. Cutoff naar Forge zonder de afleverlat te verlagen

Na een geaccepteerde relevante proef wordt het volgende geschikte geautoriseerde resultaat via Forge uitgevoerd zodra de geïnstalleerde capability die scope kan dragen. Wacht niet op de volledige Server/Console/Workspace/installer/paralleliteitsfamilie. Eén seriële proef bewijst geen cross-repo/concurrente capability.

`TRANSFERRED_TO_FORGE` krijgt de werkelijke Mission-/Actionreferenties; geen concurrerende directe prompt voor dezelfde scope. Nog niet ondersteunde uitbreidingen kunnen expliciet DIRECT_CODEX blijven. Beide routes erven dezelfde verticale DoD en het passende bestaande lifecyclemandaat. De runtime moet nog steeds echte Business/Architecture-, uitvoerings- en deliveryauthority verifiëren. Deze operatorafspraak implementeert of activeert geen nieuwe autonome productpolicy.

Na voldoende cutover worden de architectsessies Missionselectie-/reviewingangen, geen alternatieve implementatieschedulers. Geen voorgeschreven Actionlijst, nieuwe Mission zonder vrijgave of automatisch gewijzigde werklijst door reviewbevindingen.

## 9. Onderhoud en bewijsgrens

Deze aangescherpte afspraak registreert de expliciete ownerwens: één verticale aftrap volledig afmaken zonder losse DoD-/test-/refactor-/mergeprompts. Zij autoriseert geen gelijktijdige start van alle families. Ververs bij NEXT alleen relevante owning bronnen en evidence. Globale planningswijzigingen blijven reviewed documentatie; live assignmentovergangen horen in de eigen issues en echte productadministratie.

Oorspronkelijke bronreadback van de indeling: Forge `0da4ffae94f1834b957a04ea31d7ff2010fd072a`, EP `aa73aa46322230aaf8afce4223fd497879d800d6`, Workspace `5ecd418bc9cdc983791bf35c07457ffdb2ad1166`, Forge Platform `88b256b274fb20487b7c0cce05ccd5a58a4516f1`. Dat zijn historische pins, geen nieuwe installatieaudit. De toen geparkeerde EP #175 wordt niet door de nieuwe routine-machtigingsafspraak hervat.

Het verticale addendum is geschreven tegen Forge `c6c05340744ee0259c6cabba8039a42a6b7aa599`. De 165 node-ID’s, 34 families, ownership, ranks, defaultpools en owning dependencies blijven behouden. Geen runtimecode, schema, workflow, grant, credential, release, installatie, database, reset of Mission is veranderd/gestart. Documentstructuurtests bewijzen de planningsafspraak, geen reeds gerealiseerde autonome productuitvoering.
