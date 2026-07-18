from flask import Flask, render_template, request, redirect, url_for, session, flash
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import joinedload
from sqlalchemy import func
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
import os
from functools import wraps

app = Flask(__name__)

# Clave para usar session
app.secret_key = "clave_secreta_para_la_app"

# Configuración base de datos (Conectado a Clever Cloud con PyMySQL y reciclaje de conexiones)
app.config['SQLALCHEMY_DATABASE_URI'] = 'mysql+pymysql://uemwwqhigdgsxy4g:JnzC4Q25GZRhFmjzOo8V@bvgbqgbz7frvxshoum3l-mysql.services.clever-cloud.com:3306/bvgbqgbz7frvxshoum3l'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# Agregamos configuración de pool para evitar desconexiones inesperadas (Lost connection)
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "pool_recycle": 280,
    "pool_pre_ping": True
}

db = SQLAlchemy(app)

# ============================
# DECORADORES DE LOGIN Y ADMIN
# ============================

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated_function

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "usuario_id" not in session:
            return redirect(url_for("login"))
        if session.get("usuario_rol") != "admin":
            return render_template("acceso_restringido.html"), 403
        return f(*args, **kwargs)
    return decorated_function


# ============================
# MODELOS
# ============================

class Categoria(db.Model):
    __tablename__ = 'categorias'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    productos = db.relationship('Producto', backref='categoria', lazy=True)

class Producto(db.Model):
    __tablename__ = 'productos'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    descripcion = db.Column(db.Text)
    precio = db.Column(db.Numeric(10, 2), nullable=False)
    stock = db.Column(db.Integer, default=0)
    imagen = db.Column(db.String(255))
    categoria_id = db.Column(db.Integer, db.ForeignKey('categorias.id'))
    
    # Relación agregada para que el carrusel funcione en Jinja de forma fluida
    imagenes = db.relationship('ImagenProducto', backref='producto', lazy=True, cascade="all, delete-orphan")

class ImagenProducto(db.Model):
    __tablename__ = 'imagenes_productos'
    id = db.Column(db.Integer, primary_key=True)
    nombre_archivo = db.Column(db.String(255), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id', ondelete='CASCADE'), nullable=False)

class Usuario(db.Model):
    __tablename__ = 'usuarios'
    id = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(100), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    rol = db.Column(db.Enum('cliente', 'admin'), default='cliente')
    fecha_registro = db.Column(db.DateTime, server_default=db.func.now())

class Pedido(db.Model):
    __tablename__ = 'pedidos'
    id = db.Column(db.Integer, primary_key=True)
    usuario_id = db.Column(db.Integer, db.ForeignKey('usuarios.id'), nullable=False)
    fecha = db.Column(db.DateTime, server_default=db.func.now())
    total = db.Column(db.Numeric(10, 2), nullable=False)
    estado = db.Column(db.Enum('pendiente', 'pagado', 'enviado', 'cancelado', 'entregado'), server_default='pendiente')
    
    # --- DATOS DE ENVÍO ---
    destinatario = db.Column(db.String(100), nullable=True)
    telefono = db.Column(db.String(30), nullable=True)
    direccion = db.Column(db.String(255), nullable=True)
    ciudad = db.Column(db.String(100), nullable=True)
    codigo_postal = db.Column(db.String(20), nullable=True)
    provincia = db.Column(db.String(100), nullable=True)
    indicaciones = db.Column(db.Text, nullable=True)
    
    codigo_seguimiento = db.Column(db.String(100), nullable=True)

    usuario = db.relationship("Usuario", backref="pedidos")
    items = db.relationship("DetallePedido", backref="pedido", cascade="all, delete-orphan", lazy=True)

class DetallePedido(db.Model):
    __tablename__ = 'detalle_pedido'
    id = db.Column(db.Integer, primary_key=True)
    pedido_id = db.Column(db.Integer, db.ForeignKey('pedidos.id'), nullable=False)
    producto_id = db.Column(db.Integer, db.ForeignKey('productos.id'), nullable=False)
    amount_historico = db.Column(db.Integer, name="cantidad", nullable=False)
    precio_unitario = db.Column(db.Numeric(10, 2), nullable=False)

    producto = db.relationship("Producto")

    @property
    def cantidad(self):
        return self.amount_historico

    @property
    def cantidad(self):
        return self.amount_historico

    @cantidad.setter
    def cantidad(self, value):
        self.amount_historico = value


# ============================
# RUTAS DE LA TIENDA
# ============================

@app.route('/')
def index():
    busqueda = request.args.get('q', '').strip()
    orden = request.args.get('orden', '')
    categorias = request.args.getlist('categoria')
    precio_max = request.args.get('precio', 1000000000)

    query = Producto.query

    if busqueda:
        query = query.filter(Producto.nombre.like(f'%{busqueda}%'))
    if categorias:
        query = query.filter(Producto.categoria_id.in_(categorias))

    query = query.filter(Producto.precio <= precio_max)

    if orden == 'mayor':
        query = query.order_by(Producto.precio.desc())
    elif orden == 'menor':
        query = query.order_by(Producto.precio.asc())
    elif orden == 'antiguo':
        query = query.order_by(Producto.id.asc())
    else:
        query = query.order_by(Producto.id.desc())

    productos = query.all()
    categorias_db = Categoria.query.all()

    return render_template(
        "index.html",
        productos=productos,
        categorias=categorias_db,
        busqueda=busqueda,
        precio_max=precio_max
    )

@app.route("/producto/<int:id>")
def producto(id):
    prod = Producto.query.get_or_404(id)
    return render_template("producto.html", producto=prod)


# ============================
# GESTIÓN DEL CARRITO
# ============================

@app.route("/carrito")
def carrito():
    carrito = session.get("carrito", [])
    total = sum(item["precio"] * item.get("cantidad", 1) for item in carrito)
    return render_template("carrito.html", items=carrito, total=total)

@app.route("/agregar_carrito/<int:id>", methods=["POST"])
def agregar_carrito(id):
    producto = Producto.query.get_or_404(id)
    try:
        cantidad = int(request.form.get("cantidad", 1))
    except (ValueError, TypeError):
        cantidad = 1
    if cantidad < 1:
        cantidad = 1

    carrito = session.get("carrito", [])
    found = False
    for it in carrito:
        if it["id"] == producto.id:
            it["cantidad"] = it.get("cantidad", 1) + quantity
            found = True
            break
    if not found:
        carrito.append({
            "id": producto.id,
            "nombre": producto.nombre,
            "precio": float(producto.precio),
            "imagen": producto.imagen,
            "cantidad": cantidad
        })
    session["carrito"] = carrito
    return redirect(url_for("carrito"))

@app.route("/carrito/eliminar/<int:id>", methods=["POST"])
def eliminar_carrito(id):
    carrito = session.get("carrito", [])
    eliminar_todo = request.form.get("toda", "0") == "1"
    nuevo = []
    for item in carrito:
        if item["id"] != id:
            nuevo.append(item)
        else:
            if eliminar_todo:
                pass
            else:
                if item.get("cantidad", 1) > 1:
                    item["cantidad"] = item.get("cantidad", 1) - 1
                    nuevo.append(item)
    session["carrito"] = nuevo
    return redirect(url_for("carrito"))


# ============================
# FLUJO DE COMPRA REAL
# ============================

@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    carrito = session.get("carrito", [])
    if not carrito:
        return redirect(url_for("carrito"))
        
    total = sum(item["precio"] * item.get("cantidad", 1) for item in carrito)
    
    if request.method == "POST":
        destinatario = request.form.get("destinatario")
        telefono = request.form.get("telefono")
        direccion = request.form.get("direccion")
        ciudad = request.form.get("ciudad")
        codigo_postal = request.form.get("codigo_postal")
        provincia = request.form.get("provincia")
        indicaciones = request.form.get("indicaciones")
        
        insuficientes = []
        for item in carrito:
            prod = Producto.query.get(item["id"])
            amount = item.get("cantidad", 1)
            if not prod or prod.stock < amount:
                insuficientes.append(f"{prod.nombre if prod else 'ID ' + str(item['id'])} (Solicitado: {amount}, Stock: {prod.stock if prod else 0})")
        
        if insuficientes:
            mensaje = "Stock insuficiente para: " + ", ".join(insuficientes)
            return render_template("carrito.html", items=carrito, total=total, error=mensaje)
            
        nuevo_pedido = Pedido(
            usuario_id=session["usuario_id"],
            total=total,
            estado='pendiente',
            destinatario=destinatario,
            telefono=telefono,
            direccion=direccion,
            ciudad=ciudad,
            codigo_postal=codigo_postal,
            provincia=provincia,
            indicaciones=indicaciones
        )
        db.session.add(nuevo_pedido)
        db.session.flush()
        
        for item in carrito:
            pedido_item = DetallePedido(
                pedido_id=nuevo_pedido.id,
                producto_id=item["id"],
                cantidad=item.get("cantidad", 1),
                precio_unitario=item["precio"]
            )
            db.session.add(pedido_item)
            
        db.session.commit()
        return redirect(url_for("pasarela_pago", pedido_id=nuevo_pedido.id))
        
    return render_template("checkout.html", total=total)

@app.route("/pasarela_pago/<int:pedido_id>", methods=["GET", "POST"])
@login_required
def pasarela_pago(pedido_id):
    pedido = Pedido.query.get_or_404(pedido_id)
    
    if pedido.usuario_id != session["usuario_id"] and session.get("usuario_rol") != "admin":
        return redirect("/")
        
    if request.method == "POST":
        resultado = request.form.get("resultado")
        
        if resultado == "exitoso":
            pedido.estado = "pagado"
            
            for item in pedido.items:
                prod = Producto.query.get(item.producto_id)
                if prod:
                    prod.stock = max(0, prod.stock - item.cantidad)
            
            db.session.commit()
            session["carrito"] = []
            return redirect(url_for("pedido_confirmado", id=pedido.id))
        else:
            return render_template("pasarela_pago.html", pedido=pedido, error="La simulación de pago fue rechazada. Por favor, intente nuevamente.")
            
    return render_template("pasarela_pago.html", pedido=pedido)

@app.route("/pedido/<int:id>/confirmado")
@login_required
def pedido_confirmado(id):
    pedido = Pedido.query.get_or_404(id)
    return render_template("pedido_confirmado.html", pedido=pedido)


# ============================
# HISTORIAL DE PEDIDOS DEL CLIENTE
# ============================

@app.route("/mis-pedidos")
@login_required
def mis_pedidos():
    pedidos_usuario = Pedido.query.filter(Pedido.usuario_id == session["usuario_id"])\
        .options(joinedload(Pedido.items).joinedload(DetallePedido.producto))\
        .order_by(Pedido.fecha.desc()).all()
        
    return render_template("mis_pedidos.html", pedidos=pedidos_usuario, section="mis_pedidos")


# ============================
# LOGIN / REGISTRO
# ============================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")
    email = request.form["email"]
    password = request.form["password"]
    usuario = Usuario.query.filter_by(email=email).first()
    if not usuario or not check_password_hash(usuario.password_hash, password):
        return render_template("login.html", error="Email o contraseña incorrectos")
    session["usuario_id"] = usuario.id
    session["usuario_nombre"] = usuario.nombre
    session["usuario_rol"] = usuario.rol  
    return redirect("/")

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "GET":
        return render_template("register.html", active="register")
    
    nombre = request.form["nombre"]
    email = request.form["email"]
    password = request.form["password"]
    password2 = request.form["password2"]
    
    if password != password2:
        return render_template("register.html", error="Las contraseñas no coinciden")
        
    existe = Usuario.query.filter_by(email=email).first()
    if existe:
        return render_template("register.html", error="El email ya está registrado")
        
    nuevo = Usuario(
        nombre=nombre,
        email=email,
        password_hash=generate_password_hash(password),
        rol="cliente"
    )
    db.session.add(nuevo)
    db.session.commit()
    return redirect("/login")


# ============================
# PANEL DE ADMINISTRACIÓN (OPTIMIZADO)
# ============================

@app.route('/admin')
@admin_required
def admin_dashboard():
    return redirect(url_for('admin_pedidos'))

@app.route("/admin/pedidos")
@admin_required
def admin_pedidos():
    estado_filtro = request.args.get('estado', '').strip()
    
    query = Pedido.query.options(
        joinedload(Pedido.usuario),
        joinedload(Pedido.items).joinedload(DetallePedido.producto)
    )
    
    if estado_filtro:
        query = query.filter(Pedido.estado == estado_filtro)
        
    pedidos = query.order_by(Pedido.fecha.desc()).all()
    
    total_pedidos = Pedido.query.count()
    pendientes = Pedido.query.filter(Pedido.estado == 'pendiente').count()
    enviados = Pedido.query.filter(Pedido.estado == 'enviado').count()
    
    return render_template(
        "admin_pedidos.html", 
        pedidos=pedidos, 
        section="pedidos",
        estado_filtro=estado_filtro,
        total_pedidos=total_pedidos,
        pendientes=pendientes,
        enviados=enviados
    )

@app.route("/admin/pedido/<int:id>/detalle")
@admin_required
def admin_detalle_pedido(id):
    pedido = Pedido.query.get_or_404(id)
    return render_template("admin_detalle_pedido.html", pedido=pedido)

@app.route("/admin/pedido/<int:id>/despachar", methods=["POST"])
@admin_required
def admin_despachar_pedido(id):
    pedido = Pedido.query.get_or_404(id)
    codigo = request.form.get("codigo_seguimiento", "").strip()
    
    if not codigo:
        flash("Por favor, introduce un código de seguimiento válido.", "error")
        return redirect(url_for("admin_detalle_pedido", id=pedido.id))
        
    pedido.codigo_seguimiento = codigo
    pedido.estado = "enviado"
    db.session.commit()
    
    flash(f"El pedido #{pedido.id} ha sido marcado como despachado correctamente.", "success")
    return redirect(url_for("admin_pedidos"))

@app.route("/admin/pedido/<int:id>/actualizar_estado", methods=["POST"])
@admin_required
def admin_actualizar_estado_pedido(id):
    pedido = Pedido.query.get_or_404(id)
    nuevo_estado = request.form.get("estado")
    
    estados_validos = ['pendiente', 'pagado', 'enviado', 'cancelado', 'entregado']
    if nuevo_estado and nuevo_estado.lower() in estados_validos:
        pedido.estado = nuevo_estado.lower()
        db.session.commit()
        flash(f"Estado del pedido #{pedido.id} actualizado a {nuevo_estado}.", "success")
    else:
        flash("Estado inválido proporcionado.", "error")
        
    return redirect(url_for("admin_pedidos"))

@app.route("/admin/pedido/<int:id>/etiqueta")
@admin_required
def admin_etiqueta_envio(id):
    pedido = Pedido.query.get_or_404(id)
    return render_template("admin_etiqueta.html", pedido=pedido)


# ============================
# OPTIMIZACIÓN DEL REPORTE DE VENTAS
# ============================

@app.route('/admin/reportes')
@admin_required
def admin_reportes():
    metricas = db.session.query(
        func.coalesce(func.sum(Pedido.total), 0),
        func.count(Pedido.id)
    ).filter(Pedido.estado.in_(['pagado', 'enviado', 'entregado'])).first()
    
    total_facturado = float(metricas[0])
    total_pedidos_exitosos = metricas[1]
    
    total_articulos = db.session.query(
        func.coalesce(func.sum(DetallePedido.amount_historico), 0)
    ).join(Pedido).filter(Pedido.estado.in_(['pagado', 'enviado', 'entregado'])).scalar()

    ventas_mensuales = db.session.query(
        func.date_format(Pedido.fecha, '%Y-%m').label('mes_clave'),
        func.date_format(Pedido.fecha, '%M %y').label('mes_nombre'),
        func.sum(Pedido.total)
    ).filter(Pedido.estado.in_(['pagado', 'enviado', 'entregado']))\
     .group_by('mes_clave')\
     .order_by('mes_clave').all()

    meses_en = {"January": "Enero", "February": "Febrero", "March": "Marzo", "April": "Abril", 
                 "May": "Mayo", "June": "Junio", "July": "Julio", "August": "Agosto", 
                 "September": "Septiembre", "October": "Octubre", "November": "Noviembre", "December": "Diciembre"}

    labels = []
    data_ventas = []
    
    for item in ventas_mensuales:
        partes = item[1].split()
        nombre_mes = meses_en.get(partes[0], partes[0])
        labels.append(f"{nombre_mes} {partes[1]}")
        data_ventas.append(float(item[2]))

    if not labels:
        labels = ["Sin Ventas"]
        data_ventas = [0]

    return render_template(
        'admin_reportes.html', 
        section="reportes",
        labels=labels,
        data_ventas=data_ventas,
        total_facturado=total_facturado,
        total_pedidos_exitosos=total_pedidos_exitosos,
        total_articulos=total_articulos
    )


# ============================
# GESTIÓN FÍSICA DE PRODUCTOS
# ============================

@app.route('/admin/productos')
@admin_required
def admin_productos():
    productos = Producto.query.all()
    return render_template('admin_productos.html', productos=productos, section="productos")

# UNIFICADA Y REPARADA: Eliminamos el duplicado y añadimos soporte real para múltiples imágenes
@app.route('/admin/productos/editar/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_editar_producto(id):
    producto = Producto.query.get_or_404(id)
    
    if request.method == 'POST':
        producto.nombre = request.form.get('nombre')
        producto.precio = float(request.form.get('precio'))
        producto.descripcion = request.form.get('descripcion')
        producto.stock = int(request.form.get('stock'))
        
        nueva_categoria_id = request.form.get('categoria_id')
        if nueva_categoria_id:
            producto.categoria_id = int(nueva_categoria_id)
        
        # 1. Procesar cambio opcional de la Imagen Principal (Portada)
        imagen_principal = request.files.get('imagen')
        if imagen_principal and imagen_principal.filename != '':
            filename_principal = secure_filename(imagen_principal.filename)
            imagen_principal.save(os.path.join("static/img", filename_principal))
            producto.imagen = filename_principal
            
        # 2. Procesar subida de imágenes secundarias para el Carrusel
        imagenes_carrusel = request.files.getlist('imagenes_carrusel')
        for f in imagenes_carrusel:
            if f and f.filename != '':
                filename_secundario = secure_filename(f.filename)
                f.save(os.path.join("static/img", filename_secundario))
                
                # Almacenamos el registro en la base de datos de Clever Cloud
                nueva_img = ImagenProducto(nombre_archivo=filename_secundario, producto_id=producto.id)
                db.session.add(nueva_img)
                
        try:
            db.session.commit()
            flash('¡Producto e imágenes del carrusel actualizadas con éxito!', 'success')
            return redirect(url_for('admin_productos'))
        except Exception as e:
            db.session.rollback()
            flash('Error al guardar los cambios en Clever Cloud.', 'danger')
            
    categorias = Categoria.query.all()
    return render_template('admin_editar_producto.html', producto=producto, categorias=categorias)

@app.route('/admin/productos/eliminar/<int:id>', methods=['POST'])
@admin_required
def admin_eliminar_producto(id):
    producto = Producto.query.get_or_404(id)
    db.session.delete(producto)
    db.session.commit()
    return redirect(url_for('admin_productos'))

@app.route('/admin/productos/agregar', methods=['GET', 'POST'])
@admin_required
def admin_agregar_producto():
    categorias = Categoria.query.all()
    if request.method == 'POST':
        nombre = request.form['nombre']
        descripcion = request.form['descripcion']
        precio = request.form['precio']
        stock = request.form['stock']
        categoria_id = request.form['categoria_id']
        imagen_archivo = request.files.get("imagen")
        filename = None
        if imagen_archivo and imagen_archivo.filename != "":
            filename = secure_filename(imagen_archivo.filename)
            imagen_archivo.save(os.path.join("static/img", filename))
        nuevo = Producto(
            nombre=nombre,
            descripcion=descripcion,
            precio=precio,
            stock=stock,
            categoria_id=categoria_id,
            imagen=filename
        )
        db.session.add(nuevo)
        db.session.commit()
        return redirect(url_for('admin_productos'))
    return render_template('admin_agregar_producto.html', categorias=categorias, section="productos")

@app.route('/admin/productos/eliminar-multiples', methods=['POST'])
@admin_required
def admin_eliminar_productos_multiples():
    ids_a_eliminar = request.form.getlist('producto_ids')
    
    if ids_a_eliminar:
        try:
            Producto.query.filter(Producto.id.in_(ids_a_eliminar)).delete(synchronize_session=False)
            db.session.commit()
            flash(f'¡Éxito! Se eliminaron {len(ids_a_eliminar)} productos correctamente.', 'success')
        except Exception as e:
            db.session.rollback()
            flash('Error al intentar conectar con el servidor de Clever Cloud.', 'danger')
    else:
        flash('No seleccionaste ningún producto de la lista.', 'danger')
        
    return redirect(url_for('admin_productos'))

@app.route("/admin/usuarios")
@admin_required
def admin_usuarios():
    usuarios = Usuario.query.all()
    return render_template("admin_usuarios.html", usuarios=usuarios, section="usuarios")

@app.route("/admin/usuarios/eliminar/<int:id>", methods=["POST"])
@admin_required
def admin_eliminar_usuario(id):
    usuario = Usuario.query.get_or_404(id)
    db.session.delete(usuario)
    db.session.commit()
    return redirect(url_for("admin_usuarios"))

@app.route("/admin/usuarios/editar/<int:id>", methods=["GET", "POST"])
@admin_required
def admin_editar_usuario(id):
    usuario = Usuario.query.get_or_404(id)
    if request.method == "POST":
        usuario.nombre = request.form["nombre"]
        usuario.email = request.form["email"]
        usuario.rol = request.form["rol"]
        db.session.commit()
        return redirect(url_for("admin_usuarios"))
    return render_template("editar_usuario.html", usuario=usuario)


# ============================
# INICIAR SERVIDOR (LIMPIO & RÁPIDO)
# ============================

# ============================
# INICIAR SERVIDOR (LIMPIO & RÁPIDO)
# ============================

if __name__ == '__main__':
    with app.app_context():
        # CLAVE: Le ordena a SQLAlchemy crear cualquier tabla nueva que falte en Clever Cloud
        db.create_all() 

    app.run(debug=True)