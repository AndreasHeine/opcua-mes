try:
    from opcua import ua, uamethod, Server
    from opcua.server.user_manager import UserManager
    import os, sys, json, time, random
    import asyncio
    import mysql.connector
except ImportError as e:
    print(e)

project_folder = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(project_folder, "config.json")) as file:
    config = json.load(file) 

debug = config["debug"]

if config["sign&encrypt"]:
    #pyOpenSSL migth be a better way... for now i use openssl
    #i should check the cert's expiering date. if its to old i will regenerate it 
    try:
        os.system("openssl genrsa -out key.pem 2048")
        os.system("openssl req -x509 -days 365 -new -out cert.pem -key key.pem -config ssl.conf")
    except:
        raise RuntimeError("openssl requiered!")

"""
Production Planing System: mySQL database
"""
with open(os.path.join(project_folder, "pps.json")) as file:
    pps = json.load(file)

"""
OPC-UA-Usermanager
"""
with open(os.path.join(project_folder, "users.json")) as file:
    users_db = json.load(file)

def user_manager(isession, username, password):
    isession.user = UserManager.User
    return username in users_db and password == users_db[username]

"""
OPC-UA-Methods
"""
@uamethod
def get_next_order(parent, id):
    db = mysql.connector.connect(
        host=pps["ip"],
        user=pps["user"],
        passwd=pps["password"],
        database=pps["dbname"]
    )
    cursor = db.cursor(prepared=True)
    cursor.execute(f"""SELECT * FROM {pps["table"]} WHERE order_id = %s""", (id, )) #always use injection safe querys!!!
    row = cursor.fetchone()
    cursor.close()
    db.close()
    if row:
        id=id
        status=row[1]
        #....
    else:
        id=0
        status=0
    if debug:
        print("Method-Call -> Req-ID: " + str(id) + " Dataset: " + str(row))
    return  (
                ua.Variant(id, ua.VariantType.Int64),
                ua.Variant(status, ua.VariantType.Int64)
                #....
            )

"""
OPC-UA-Server Setup
"""
server = Server()
server.set_endpoint("opc.tcp://" + config["ip"] + ":" + config["port"])
server.set_server_name(config["servername"])
address_space = server.register_namespace("http://andreas-heine.net/UA")
server.set_application_uri(config["uri"])
if config["sign&encrypt"]:
    server.load_certificate("cert.pem")
    server.load_private_key("key.pem")
    server.set_security_policy([ua.SecurityPolicyType.Basic256Sha256_SignAndEncrypt])
else:
    server.set_security_policy([ua.SecurityPolicyType.NoSecurity])
server.set_security_IDs(["Username"])
server.user_manager.set_user_manager(user_manager)

"""
OPC-UA-Modeling
"""
root_node = server.get_root_node()
object_node = server.get_objects_node()
server_node = server.get_server_node()

parameter_obj = object_node.add_object(address_space, "Parameter")
random_node = parameter_obj.add_variable(address_space, "random", ua.Variant(0, ua.VariantType.UInt64))

methods_obj = object_node.add_object(address_space, "Methods")
get_order_node = methods_obj.add_method(    address_space, 
                                            "get_next_order", 
                                            get_next_order, 
                                            [
                                                #Input-Arguments:
                                                ua.VariantType.Int64    #ID
                                                #....
                                            ], 
                                            [
                                                #Output-Arguments:
                                                ua.VariantType.Int64,   #ID
                                                ua.VariantType.Int64    #STATUS
                                                #....
                                            ]
                                        )

"""
OPC-UA-VarUpdater
"""

#for me async eventloop works just fine, you could also use threads for that!

async def servicelevel_updater(servicelevel_node):
    value = 0
    while True:
        await asyncio.sleep(1)
        #no redundant servers!
        if value < 200:
            value = 250
            servicelevel_node.set_value(ua.DataValue(ua.Variant(value, ua.VariantType.Byte)))

async def random_updater(random_node):
    while True:
        await asyncio.sleep(random.randint(1,10))
        random_node.set_value(ua.DataValue(ua.Variant(random.randint(70,90), ua.VariantType.UInt64)))
            
loop = asyncio.get_event_loop()
asyncio.ensure_future(servicelevel_updater(server.get_node("ns=0;i=2267")))
asyncio.ensure_future(random_updater(random_node))

"""
OPC-UA-Server Start
"""
if __name__ == "__main__":
    try:
        server.start()
        loop.run_forever()            
    except KeyboardInterrupt:
        loop.close()
        server.stop()
