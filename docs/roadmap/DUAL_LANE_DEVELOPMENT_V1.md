# Twee ontwikkelsporen tot Forge het werk overneemt

**Vastgelegd:** 18 september 2026. **Status:** owner-requested tijdelijke werkindeling; geen nieuwe productruntime, Missionlijst of uitvoeringsautorisatie. **NO_BUMP.**

Doel: maximaal twee onafhankelijke Codex-uitvoeringsopdrachten tegelijk, vanuit twee blijvende architectsessies. `ARCHITECT_1` bedient `LANE_1`; `ARCHITECT_2` bedient `LANE_2`. Na eenmalige initialisatie volstaan **“geef volgende prompt (1)”** en **“geef volgende prompt (2)”**. Het aantal aftrappen is geen succesmaat: het doel blijft zo vroeg mogelijk geschikte werkpakketten door Forge laten afleiden en via EP uitvoeren.

Deze indeling is nieuw, op verzoek van de eigenaar. Zij ordent de bestaande [inventaris en focus](ROADMAP_OVERVIEW_AND_AUTONOMY_FOCUS.md), maar verandert geen harde afhankelijkheden, peer-eigenaarschap, geparkeerde besluiten of Mission-3-criteria. De [machineleesbare indeling](dual-lane-development-v1.json) verwijst naar alle 165 analytische tel-eenheden uit de 34 families, met de zeven gezamenlijke nodes eenmaal. De oorspronkelijke snapshot van 17 september blijft ongewijzigd en is geen audit van wat vandaag nog ongebouwd is.

## 1. Twee rollende rijen, geen verplichte gezamenlijke rondes

| Sessierouter | Primair werk | Onafhankelijke terugval | Gedeelde registratie |
| --- | --- | --- | --- |
| [LANE_1](lanes/LANE_1.md) | Forge: autonomie, zelfstandige services, planning en projectloop | Forge Platform: nuttige, reeds geautoriseerde contract-/read-only-/compositionslice | [Forge #141](https://github.com/pcvantol/forge/issues/141) |
| [LANE_2](lanes/LANE_2.md) | EP: correcte/efficiënte uitvoering en parallelle Actions | Workspace: eigen Server/API/contract-/fixturewerk, daarna gekwalificeerde consumers | [Forge #142](https://github.com/pcvantol/forge/issues/142) |

Dit zijn standaard repositoryhouders, geen permanente productteams. De twee pools overlappen niet, zodat gelijktijdige NEXT-aanvragen niet dezelfde repository kunnen claimen. Zonder expliciete overdracht schrijft lane 1 niet in EP/Workspace en lane 2 niet in Forge/Forge Platform. Een sessie mag vrij tussen haar eigen vrije repositories kiezen. Een andere verdeling, bijvoorbeeld Workspace in lane 1 en EP in lane 2, kan via de korte overdrachtsprocedure hieronder; geen nieuwe architectuurwijziging nodig.

Een lane die klaar is, hoeft niet op de andere te wachten. Zij kiest de hoogst geprioriteerde **werkelijk uitvoerbare** subset. Een geblokkeerde dependency wordt niet omzeild; de vrije lane pakt ander zinvol werk. Wanneer geen veilige, geautoriseerde combinatie beschikbaar is, is `WAIT` correct. “Altijd twee” is een benuttingsdoel, geen reden om werk te verzinnen, scopes te vergroten of kritieke gedeelde resources te overbelasten. Er zijn geen doorlooptijdschattingen die een mathematisch optimale verdeling bewijzen.

## 2. Eerste werkvolgorde en concrete combinaties

Dit is een rollende voorkeursvolgorde, geen nieuw execution-DAG of vast aantal prompts. Actuele producer-evidence gaat vóór de voorbeeldrij; contract-first implementatie kan eerder dan finale integratie worden geleverd als de owning roadmap dat toestaat.

| Moment / prioriteit | LANE_1 | LANE_2 | Voorwaarde / reden dat dit kan overlappen |
| --- | --- | --- | --- |
| Huidige voorbereiding | Bestaande reset-`prepare → revalidate`-correctie adopteren/afronden als zij nog niet geleverd is; niet opnieuw starten | Eerst een kleine Workspace `WH-CONTRACT`-slice wanneer EP nog door die correctie nodig kan zijn; anders ontbrekende EP `SA-CTX`/`SA-ISO`-slice | Geen gedeelde bronwriter. Onderhoud/EP-scope eerst vaststellen; lege PR-lijst bewijst geen vrije lokale sessie. |
| Echte clean-preflight en Mission 3 | Alleen het bestaande expliciet geautoriseerde testcontract; target-main, beide runtimeversies en echte datasetresources reserveren | Workspace eigen contract-/servicewerk op geïsoleerde fixtures; geen EP-/Forge-installatie of testtargetmutatie | Runtime- en baselinefreeze geldt over beide lanes. Geen nieuwe testcriteria; geen resetautorisatie door deze tabel. |
| Na beoordeling van de live proef | Server-only `FSH-SERVICES` met benodigde `FH-*`-delen; ontbrekende `FCI-*`-regressiedekking als begrensde sublevering | Resterende echte EP context-/invocation-isolatie en observatiebewijs; daarna toepasselijke deterministische controls | Gescheiden repositories en fixtures; finale activatie in afgesproken kort onderhoudsvenster. Niet eerst de hele Console of SA-familie eisen. |
| Paralleliteit voorbereiden | `PA-F0`, daarna `PA-F1/PA-F2` | Na beschikbaar Forge `PA-F0`: `PA-E0 → PA-E1 → PA-E2/PA-E3`; `PA-E4` volgens eigen DAG | EP wacht op het contract, niet op complete Forge-paralleliteit. Forge state/planning kan naast EP-uitvoering groeien. |
| Paralleliteit aansluiten | `PA-F3` zodra vereiste EP-subsets bewezen zijn; daarna `PA-F4/PA-F5` | EP negatieve cases/readback en `PA-EQ` | Geen Forge-consumer-PASS uit mocks alleen; gekoppelde kwalificatie gebruikt exact de juiste artifacts. |
| Werkvoorraad zonder eigenaar-als-berichtenbus | Kleinste `PRM-F-*` manual/approved-worklist-slice en passende `FCO-*` | Relevante EP policy/progression/receipt-subsets; anders Workspace read-only project-/beslisprojectie | Projectloop hoeft niet op complete Actionparalleliteit of volledige delegatie te wachten; oorspronkelijke PRM/FCI/FCO-edges blijven gelden. |
| Overdrachtsmoment | Volgende ondersteunde scope als **Forge-Missionaftrap** in plaats van directe implementatieprompt | Zelfde keuze per scope; directe Codex alleen voor aantoonbaar nog niet door Forge gedragen werk | Niet wachten op alle 34 families. Twee Codex-lanes geven geen bevoegdheid om twee product-Missions parallel te starten wanneer de runtime dat nog niet ondersteunt. |

De canonieke bronnen voor deze slices zijn [runtime-evolutie](../architecture/runtime-evolution-roadmap.md), [inner-loop CI](FORGE_INNER_LOOP_CI_V1.md), [Forge-paralleliteit](PARALLEL_ACTION_RUNTIME_V1.md), [EP-paralleliteit](https://github.com/pcvantol/engineering-platform/blob/main/docs/development/PARALLEL_ACTION_EXECUTION_V1_DAG.json), [projectloop](LIVE_PROJECT_ROADMAP_MANAGEMENT_V1.md), [EP-efficiëntie](https://github.com/pcvantol/engineering-platform/blob/main/docs/development/SUBAGENT_ORCHESTRATION_V1_ROADMAP.md) en [Workspace-HTTP](https://github.com/pcvantol/workspace/blob/main/docs/WORKSPACE_HTTP_API_V1_DAG.json). Raadpleeg vóór selectie de actuele, exact gepinde ownerbron; deze links zijn navigatie, geen automatisch bewijs van implementatie.

**Bestaand werk adopteren:** de completion record van Forge #140 beschrijft een vóór reset-apply afgebroken voorbereiding, geen gestarte Mission. Er is daarna al een herstelprompt uitgegeven. De eerste lane-initialisatie moet vaststellen of die nu loopt of al klaar is. Alleen de afgesproken ontbrekende slice telt als nieuw werk; de release/installatie van 2.7.22 en EP #271/#272 worden niet opnieuw geopend vanwege een oude inventarisstatus. Het oudere resetverslag is geen huidige installatiestatus.

## 3. Alle families hebben een plek, maar niet alles moet vóór cutoff

De JSON wijst alle twaalf Forge-families en vier Forge Platform-families standaard aan lane 1 toe (82 eigen rollup-eenheden). Alle negen EP-families en negen Workspace-families gaan naar lane 2 (76 eigen eenheden). De zeven gezamenlijke nodes blijven gezamenlijke bewijsjoins, met lane 1 als communicatiecoördinator; hun productcode wordt door de respectieve repositoryhouder geleverd. 82/76 is geen uren- of tokenverdeling.

Binnen elk product staat autonomie-ondersteunend werk vooraan. De grote resterende families — volledige Console, geavanceerd modelbeleid, rijke gesprekken, universele installer en nieuwe-projectbootstrap — zijn een **reservehorizon / toekomstige Forge-werklijst**, geen verplicht direct-Codexprogramma. Selecteer ze alleen als zij aantoonbaar de overdracht versnellen of een vrije lane onafhankelijk nuttig houden zonder de primaire lijn te vertragen. Geen oppervlakkig documentatiewerk maken uitsluitend om twee groene lanevakjes te tonen.

De JSON-rang is prioriteit, niet een dependency-edge. Eén familie kan meerdere samenhangende aftrappen nodig hebben. De 29 in het oude telmodel samengevoegde records blijven in de snapshot beschikbaar; vooral `FSH-SERVICES` kan als echte praktische sublevering worden gekozen zonder de rest van `FOC-*` af te maken. De onderhoudscorrectie en Mission-3-proef zijn carry-overwerk, geen stil toegevoegde 166e/167e roadmapnode.

## 4. Wat “geef volgende prompt (1/2)” precies doet

Elke aanvraag leest eerst de actuele `main`-versie van dit document, de JSON, beide lane-issues, relevante PRs/branches en de bestaande eigen opdracht. Chatgeheugen of alleen de laatste regel van het andere issue is niet voldoende bij een conflict. Gebruik lokale readback uitsluitend wanneer die werkelijk toegankelijk is; onbekende lokale activiteit is geen bewijs van leegte.

1. **Reconcileer eigen vorige aftrap.** `ISSUED` of `RUNNING` betekent geen tweede opdracht. Een herhaalde vraag retourneert dezelfde assignment of haar status. `BLOCKED`/onzekere uitkomst houdt relevante reserveringen vast totdat de owning werkboom/processen veilig zijn gepauzeerd en dat is vastgelegd. Een PR-merge alleen sluit een gevraagde release/installatie/kwalificatie niet.
2. **Toets cutoff per scope.** Kan de geïnstalleerde en gekwalificeerde Forge-route dit geautoriseerde doel inmiddels dragen? Geef dan een Missionaftrap zonder voorgeschreven Actionlijst. Leg bij een directe Codex-opdracht precies vast welk nog ontbrekend productvermogen de uitzondering rechtvaardigt.
3. **Selecteer een ready subset.** Eerst concrete autonomieblokkade, dan producerwerk dat de andere lane ontsluit, dan hoogst relevante ready subset in de primaire repo, daarna veilige fallback. Raadpleeg alle echte owning predecessors, huidige grants/parkeringen en exacte bron-/artifact-/installed-evidence. Een sample fixture kan ontwikkeling toelaten, niet een ontbrekende live contractgate aftekenen.
4. **Controleer repo en resources.** Eigen pool of bevestigde tijdelijke overdracht; geen andere actieve mutator, conflicterende branch, gedeelde testdatabase, poort, signingrunner, releaseversie of runtime-update. Reserveer vóór uitgifte, niet pas bij het maken van een PR.
5. **Schrijf en lees de eigen registratie terug.** Verhoog de issue-revision en bewaar de vorige opdracht in de historie. Neem assignment-ID, node/subset, exacte scope, bronpins, acceptatie, bevoegdheidsgrens, resource-reserveringen en resultaatlocatie op. Geef de prompt pas terug nadat die eigen registratie klopt en de peerregistratie niet conflicteert.
6. **Geef precies één volledige uitvoeringsprompt.** “Geef prompt” selecteert en reserveert; het start zelf geen provider, Mission, reset of release. De gebruiker geeft de gegenereerde scope aan de uitvoerende sessie vrij volgens de bestaande regels. Voeg geen stille automatische keten van volgende prompts toe.

Ontbreekt actuele lees-/schrijftoegang tot de gedeelde registratie, claim geen succesvolle reservering. Geef een concrete blokkade, geen plausibel verzonnen volgende opdracht. Een kapotte tijdelijke registratieroute rechtvaardigt geen omzeiling van productgovernance.

## 5. Gedeelde registratie zonder een derde scheduler te bouwen

De twee GitHub-issues zijn lichte aftrap-/handoffregistraties, **geen atomische database, distributed lock of vervanging van EP-leases**. Veiligheid rust op twee expliciete werkafspraken plus echte product-/repositorylocks: precies één architectschrijver per lane, en disjuncte repositoryhouders. Geen gelijktijdige tweede `ARCHITECT_1` of `ARCHITECT_2`. Bij overdracht van een sessie moet de oude aantoonbaar stoppen; stilte/een timestamp maakt geen resource vrij.

De architect is de enige schrijver van de assignmentregistratie. Een executor schrijft zijn geschoonde resultaat naar de gekoppelde PR of afgesproken handoff; hij geeft zichzelf geen volgende aftrap. De architect verwerkt dat resultaat bij de volgende aanvraag. Indien resultaat alleen in een privaat lokaal receipt staat, blijft de publieke registratie een veilige referentie/attestatie en geen onafhankelijk herhaalbare live-audit.

Minimum per assignment:

```text
lane / registration_revision / assignment_id / plan_revision
state: ISSUED | RUNNING | REVIEW | WAITING_DEPENDENCY | BLOCKED |
       PAUSED_SAFE | COMPLETED | CANCELLED_SAFE | TRANSFERRED_TO_FORGE
objective / exact_node_subset / source_pins / unchanged_acceptance
repository_scope / source_write_reservations / runtime_resource_reservations
execution_mode: DIRECT_CODEX | FORGE_MISSION_KICKOFF
dependency_evidence / actual_authority / expected_delivery_evidence
owning_PRs / candidate_SHA / merge_SHA / public_artifact_evidence
remaining_effects_or_locks / sanitized_result_reference
```

De initiële issues staan bewust `UNASSIGNED_NEEDS_RECONCILIATION`; dat is geen claim dat er geen lokaal werk loopt. Een issue-revision is een werkafspraak, geen CAS-garantie van GitHub. Oude evidence en uitgiftes mogen niet worden weggepoetst. Een gesloten issue of groene checkbox is geen productacceptatie. Beide lanes kunnen hun eigen issue actualiseren zonder een PR in Forge's drukke bronwerkboom; zij wijzigen niet elkaars register of de globale planningsbestanden.

### Repository tijdelijk overdragen

Binnen de vastgelegde scope mag repositoryverdeling wijzigen zonder de gebruiker als berichtenbus te gebruiken. De requester meldt in zijn eigen issue een transfer-ID, nieuwe epoch, repo en begrensde scope. De huidige houder toont in zijn eigen register `PAUSED_FOR_TRANSFER`, verifieert dat geen actieve/issued executor, auto-merge of runtime-effect die repo nog kan muteren, en geeft exact die overdracht vrij. De ontvanger leest die vrijgave terug en bevestigt dezelfde transfer/epoch vóór uitgifte. De oude houder mag vanaf vrijgave geen eigen opdracht op die repo starten, ook niet als ontvangst nog onzeker is. Bij onduidelijkheid blijft de repo gereserveerd, niet van twee lanes tegelijk.

Teruggave gebeurt omgekeerd: ontvanger verifieert quiescence en schrijft RELEASE; oorspronkelijke houder bevestigt terugname. Geen timeout, “ik zie geen PR” of lege lane betekent automatische terugname. Conflicterende epochs of twee gelijktijdige overdrachten stoppen beide betrokken selecties. Bij selectie van een gevoelig nieuw effect of scopeuitbreiding blijft echte ownerapproval nodig. Deze afspraak is handmatige/agent-gevolgde coördinatie, geen geleverd automatisch lockprotocol.

Een cross-product implementatieprompt die beide pools nodig heeft, wordt bij voorkeur opgesplitst in twee owning prompts met één gedeeld contract. Wanneer de bestaande herstelopdracht al beide nodig heeft, adopteer haar en reserveer die repos; de andere lane kiest Workspace/Forge Platform of wacht. Maak niet alsnog een derde implementatiespoor in een al gereserveerde repo.

## 6. Bronparalleliteit is niet installatieparalleliteit

Verschillende worktrees bewijzen niet dat twee writers in dezelfde repository veilig zijn. Houd vóór de gekwalificeerde parallel-capability één muterende aftrap per canonieke repository; de lanes mogen elkaars featurebranch, main, stash of cleanup niet gebruiken. Vertrouw niet op dezelfde dagelijkse checkout als beide sessions' startdirectory.

Scheid fixtures, testdatabases, poorten en scratch. Een gedeelde runner, packageaccountlimiet, signingcontext of schaarse lokale resource kan tijdelijk serialisatie vereisen. Reserveer releaseversies en productpublicatie bij één eigenaar. Geen brede test-/installatieopdracht uit een fallbacklane die ongemerkt Forge/EP-releases of credentials bijwerkt.

**Live reset/E2E-venster:** beide lanes leggen vooraf hetzelfde expliciete venster vast in hun issues. De uitvoerende lane reserveert de testtarget-main, geselecteerde installaties en werkelijke gedeelde resources; de peer bevestigt dat conflicterende effecten ontbreken. De tweede lane kan doorgaan met expliciet onafhankelijke Workspace-/Platformbron op fixtures. Geen merge in de canarytarget, artifactactivatie, serviceherstart, reset, peerconfiguratiewijziging of gedeelde datasetmutatie tijdens T0..terminal-reconciliatie. EP-bronontwikkeling tijdens de proef kan alleen wanneer vooraf expliciet bewezen buiten alle proefbaselines/resources en zonder activatie; geen automatische aanname. Na een gemeten failure blijft dezelfde proef zichtbaar mislukt; een tweede lane mag haar niet wegpoetsen.

Voor korte release-/installatiewindows is dezelfde tweezijdige afspraak nodig als de andere lane dezelfde runtime gebruikt. Installatie mag wachten terwijl onafhankelijke bronontwikkeling doorgaat; geblokkeerde activatie verandert een goede merge niet in mislukt bronwerk. Tegelijk blijft een volledig gevraagde installed oplevering onvoltooid tot echte readback.

## 7. Outputcontract van iedere gegenereerde prompt

Bovenaan: lane, assignment-ID, registry-issue, planrevisie, productrepo, concrete doel-/nodesubset en bronpin. Daarna één samenhangende scope met nog ontbrekende implementatie, verplichte tests/reviews, daadwerkelijke deliverygrens (bron, artifact, installed of live), gedeelde gereserveerde resources en stopgrenzen. Geen nieuwe architectuurcampagne wanneer de vraag een bestaande begrensde fix betreft.

Verplicht: lees eigen projectregels; bewaar ander werk; geen peer-SQL/CLI als producttransport; geen onbevoegde runtimeactivatie; sluit bestaande finding IDs met bewijs; markeer delivered versus available-to-consumer apart; maak de gevraagde geschoonde handoff/PR vindbaar voor beide architectsessies. Het rapport vermeldt wat nog niet uitgevoerd is. Een defect buiten de scope wordt een voorstel, geen automatisch voorranghebbende nieuwe opdracht.

Publieke issues/commits/PRs bevatten alleen geschikte publieke bron-/artifactreferenties en consistente aliases. Geen werkelijke lokale paden, host-/runtime-/consumeridentiteiten, Keychainrefs, lokale backup-/plan-/databasedigests of secrets. Volledig operationeel bewijs blijft beveiligd lokaal. Scan vóór de eerste push, niet pas vóór PR-aanmaak. De eerder blootgestelde branch is geen onderwerp van dit plan; geen history rewrite of cleanupopdracht.

## 8. Cutoff: stop direct-Codexwerk zodra Forge die scope kan dragen

De eerste relevante live-proef bewijst alleen haar eigen scope. Gebruik vervolgens het volgende geschikte, geautoriseerde werkpakket als Forge-Mission zodra de noodzakelijke installed capabilities en acceptatie daarvoor bestaan. Wacht niet op volledige Server/Console/Workspace/installer/paralleliteit wanneer de ondersteunde productroute de specifieke scope al kan uitvoeren. Omgekeerd mag één geslaagde seriële Mission niet als bewijs van parallelle of cross-repositorycapaciteit worden gebruikt.

Markeer overgedragen opdrachten als `TRANSFERRED_TO_FORGE` met hun echte Mission-/Actionreferenties; geef geen concurrerende directe prompt uit voor dezelfde scope. Andere nog niet ondersteunde capability-uitbreidingen kunnen tijdelijk in de vrije Codex-lane blijven, met exacte uitzondering. Bij voldoende cutover zijn beide architectsessies Missionselectie-/reviewingangen, geen alternatieve implementatie-orchestrators. Bestaande Business/Architecturegoedkeuring, werklijstbegrenzing en EP-admission blijven gelden; dit plan activeert geen volledige autonome development mode.

## 9. Onderhoud en bewijsgrens

De eigenaar heeft deze tweesporenindeling gevraagd, niet uitvoering van alle reservefamilies. Actualiseer bij iedere NEXT alleen de betrokken node-/bron-/resultaatgegevens, niet de hele inventaris. Globale lane-/scopewijzigingen worden als kleine reviewed planningswijziging bewaard; statusovergangen blijven in de eigen issues en owning bewijsadministratie. Issues en de JSON vormen geen nieuwe runtimebron voor Forge.

Bronreadback voor deze notitie: Forge `0da4ffae94f1834b957a04ea31d7ff2010fd072a`, EP `aa73aa46322230aaf8afce4223fd497879d800d6`, Workspace `5ecd418bc9cdc983791bf35c07457ffdb2ad1166`, Forge Platform `88b256b274fb20487b7c0cce05ccd5a58a4516f1`. De remote Forge/Workspace PR-lijsten waren leeg; EP #175 was nog draft/geparkeerd. Lokale uitvoering en geïnstalleerde onderhoudsfix zijn hier niet opnieuw geaudit. Oudere resetverslagen bewijzen geen huidige installatiestatus. Een geparkeerde PR is geen vrijbrief tot hervatting.

Deze levering voegt documentatie, een lane-toewijzingsindex, twee sessierouters en twee lege coördinatieregistraties toe. Geen runtimecode, schema, workflow, release, credential, operationele database, reset of Mission gestart. De structuurtest bewijst dekking van de inventaris en consistente standaardhouders, niet dat twee echte Codex-sessies al gelijktijdig hebben uitgevoerd.
