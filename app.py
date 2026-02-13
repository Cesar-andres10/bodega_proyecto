from flask import Flask, render_template, request, redirect, url_for
import pandas as pd
import sqlite3
from datetime import date

app = Flask(__name__)

# ===============================
# 🔐 CONFIGURACIÓN GENERAL
# ===============================

DB = "stock.db"          # Nombre base de datos
CLAVE_STOCK = "bodega123"  # 🔑 Clave para cargar Excel


# ===============================
# 📦 CONEXIÓN A BASE DE DATOS
# ===============================

def get_db():
    return sqlite3.connect(DB)


# ===============================
# 🧱 CREACIÓN DE TABLAS
# ===============================

with get_db() as conn:
    c = conn.cursor()

    # Tabla principal de productos
    c.execute("""
    CREATE TABLE IF NOT EXISTS stock_productos (
        sku TEXT,
        modelo TEXT,
        categoria TEXT,
        talla TEXT,
        stock INTEGER,
        ean TEXT,
        precio REAL
    )
    """)

    # Tabla historial diario
    c.execute("""
    CREATE TABLE IF NOT EXISTS historial_movimientos (
        fecha TEXT,
        sku TEXT,
        talla TEXT,
        stock_anterior INTEGER,
        stock_actual INTEGER,
        vendido INTEGER
    )
    """)

    conn.commit()


# ===============================
# 🏠 PANTALLA PRINCIPAL
# ===============================

@app.route("/")
def index():
    return render_template("index.html")


# ===============================
# 📥 CARGAR EXCEL
# ===============================

@app.route("/cargar_excel", methods=["POST"])
def cargar_excel():

    clave = request.form.get("clave")
    archivo = request.files.get("archivo")

    # Validar clave
    if clave != CLAVE_STOCK:
        return "❌ Clave incorrecta"

    if not archivo:
        return "❌ No se subió archivo"

    # 🔧 Leer Excel como texto (evita problemas con EAN)
    df = pd.read_excel(archivo, dtype=str)

    # 🔧 Limpiar espacios y valores nulos
    df = df.fillna("")
    df.columns = df.columns.str.strip().str.lower()  # Normalizar nombres
    df = df.apply(lambda x: x.str.strip())

    # 🔥 Mapeo flexible de columnas (tolera tildes y variaciones)
    df = df.rename(columns={
        "modelo": "sku",
        "texto breve de material": "modelo",
        "categoria": "categoria",
        "categoría": "categoria",
        "tamaño principal": "talla",
        "libre utilización": "stock",
        "codigo ean/upc": "ean",
        "código ean/upc": "ean",
        "valor total": "precio"
    })

    # 🔥 Verificar que existan las columnas necesarias
    columnas_necesarias = ["sku", "modelo", "categoria", "talla", "stock", "ean", "precio"]

    for col in columnas_necesarias:
        if col not in df.columns:
            return f"❌ Falta la columna: {col} en el Excel"

    # Quedarse solo con las columnas necesarias
    df = df[columnas_necesarias]

    with get_db() as conn:
        c = conn.cursor()

        # Obtener stock anterior
        c.execute("SELECT sku, talla, stock FROM stock_productos")
        stock_anterior = {(s, t): st for s, t, st in c.fetchall()}

        # Borrar stock actual
        c.execute("DELETE FROM stock_productos")

        for _, row in df.iterrows():

            sku = str(row["sku"]).strip()
            talla = str(row["talla"]).strip()

            # Convertir stock seguro
            try:
                stock = int(float(row["stock"]))
            except:
                stock = 0

            anterior = stock_anterior.get((sku, talla), 0)
            vendido = max(anterior - stock, 0)

            # Guardar historial
            c.execute("""
                INSERT INTO historial_movimientos
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                str(date.today()),
                sku,
                talla,
                anterior,
                stock,
                vendido
            ))

            # Limpiar EAN (evita .0)
            ean_limpio = str(row["ean"]).replace(".0", "").strip()

            # Convertir precio seguro
            try:
                precio_limpio = float(str(row["precio"]).replace(",", "."))
            except:
                precio_limpio = 0.0

            # Insertar producto
            c.execute("""
                INSERT INTO stock_productos
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                sku,
                row["modelo"],
                row["categoria"],
                talla,
                stock,
                ean_limpio,
                precio_limpio
            ))

        conn.commit()

    return redirect(url_for("index"))


# ===============================
# 🔍 BUSCAR PRODUCTO (MEJORADO)
# ===============================

@app.route("/buscar", methods=["POST"])
def buscar():

    codigo = request.form.get("codigo", "").strip()

    with get_db() as conn:
        c = conn.cursor()

        # 🔥 Buscar primero por EAN
        c.execute("""
            SELECT sku, modelo, categoria, precio
            FROM stock_productos
            WHERE ean = ?
            LIMIT 1
        """, (codigo,))
        producto = c.fetchone()

        # 🔥 Si no encuentra por EAN, buscar por SKU
        if not producto:
            c.execute("""
                SELECT sku, modelo, categoria, precio
                FROM stock_productos
                WHERE sku = ?
                LIMIT 1
            """, (codigo,))
            producto = c.fetchone()

        if not producto:
            return "❌ Producto no encontrado"

        sku_encontrado, modelo, categoria, precio = producto

        # 🔥 Traer todas las tallas del SKU
        c.execute("""
            SELECT talla, stock
            FROM stock_productos
            WHERE sku = ?
        """, (sku_encontrado,))
        tallas_db = c.fetchall()

    tallas = []

    for talla, stock in tallas_db:

        if stock > 5:
            color = "verde"
        elif 3 <= stock <= 5:
            color = "amarillo"
        else:
            color = "rojo"

        tallas.append({
            "talla": talla,
            "stock": stock,
            "color": color
        })

    stock_total = sum(t["stock"] for t in tallas)

    return render_template(
        "producto.html",
        modelo=modelo,
        categoria=categoria,
        precio=precio,
        stock_total=stock_total,
        tallas=tallas
    )


# ===============================
# 📊 HISTORIAL DEL DÍA
# ===============================

@app.route("/historial")
def historial():

    hoy = str(date.today())

    with get_db() as conn:
        c = conn.cursor()

        c.execute("""
            SELECT sku, talla, vendido
            FROM historial_movimientos
            WHERE fecha = ? AND vendido > 0
        """, (hoy,))
        movimientos = c.fetchall()

    total_vendido = sum(m[2] for m in movimientos)

    return render_template(
        "historial.html",
        movimientos=movimientos,
        total_vendido=total_vendido,
        fecha=hoy
    )


if __name__ == "__main__":
    app.run()
