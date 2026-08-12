COMPOSE := docker compose
DEV     := -f docker-compose.yml -f docker-compose.dev.yml

.DEFAULT_GOAL := help
.PHONY: help up down dev logs ps test shell psql secrets clean fclean re

help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

up: .env ## Lance toute la stack (equivalent du rendu : docker compose up --build)
	$(COMPOSE) up --build

down: ## Arrete la stack
	$(COMPOSE) down

dev: .env ## Lance la stack avec rechargement du code (dev local uniquement)
	$(COMPOSE) $(DEV) up --build

logs: ## Suit les logs de tous les services
	$(COMPOSE) logs -f

ps: ## Etat des services
	$(COMPOSE) ps

test: ## Lance la suite de tests Django dans le conteneur backend
	$(COMPOSE) exec backend python manage.py test

shell: ## Shell Python Django
	$(COMPOSE) exec backend python manage.py shell

psql: ## Console PostgreSQL
	$(COMPOSE) exec postgres psql -U $${POSTGRES_USER:-transcendence} -d $${POSTGRES_DB:-transcendence}

.env: ## Cree .env depuis .env.example s'il n'existe pas
	@test -f .env || (cp .env.example .env && echo "[make] .env cree — lance 'make secrets'")

secrets: .env ## Remplace toutes les valeurs change-me par des secrets aleatoires
	@python3 tools/gen_secrets.py .env

clean: ## Arrete la stack et supprime les conteneurs
	$(COMPOSE) down --remove-orphans

fclean: ## Arrete tout ET supprime les volumes (base de donnees incluse)
	$(COMPOSE) down --remove-orphans --volumes --rmi local

re: fclean up ## Rebuild complet depuis zero
