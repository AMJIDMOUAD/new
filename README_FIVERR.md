# Umbrella-1 Master Handoff (11 Apps)

This repo bundles the first 11 apps into the Umbrella-1 deployment.

## Deployment Order
1. remi-dad (api: 8110, dash: master)
2. remi-cat (api: 8111, dash: master)
3. remi-master-dashboard (api: 8112, dash: 9112)
4. smith-agency-ai (api: 8113, dash: master)
5. real-estate-hack (api: 8114, dash: master)
6. leapqos (api: 8115, dash: master)
7. kristos (api: 8116, dash: master)
8. exoverse-web4 (api: 8117, dash: master)
9. citybuzz-local (api: 8118, dash: master)
10. leappay (api: 8119, dash: master)
11. kaboi (api: 8120, dash: master)

## Contractor Instructions
1. Unzip into your working repo.
2. Run:
   make import
   make up
   make status
3. All apps will auto-stage into the master dashboard.
