# webservice_guacservice
# Cette application :
# ---->Créer le user dans guacamole
# ---->Supprime les users precedents ayant le meme prefixe
# ------> Mysql
# ------> Dyanmodb
# ----> Crée le user dans guacamole et l'insere
# exemple: curl -X POST https://webservice-guacservice.onrender.com/create-user \
#   -H "Content-Type: application/json" \
#   -d '{"email": "testuser@example.com"}'
