from app.db.sqlite import Database, init_db


def consultar_diagnostico(pppoe_user):
    db = Database()
    try:
        init_db()  # asegura el esquema antes de cualquier operación
        resultado = db.get_diagnosis(pppoe_user)
        db.close()
        
        
        
        
        
        return resultado
    except Exception as e:
        db.close()
        return {"error": str(e)}
