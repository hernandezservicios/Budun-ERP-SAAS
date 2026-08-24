# Guía paso a paso — Windows + PostgreSQL + pgAdmin 4 + Django

> Claude debe intentar automatizar todo lo posible. Esta guía existe para las acciones que pueden requerir credenciales, confirmación o interacción con la aplicación gráfica pgAdmin 4.

## 1. Verificar PostgreSQL

Claude debe detectar versión, servicio y puerto reales.

```powershell
psql --version
Get-Service *postgres*
```

Si `psql` no está en PATH, Claude debe localizar la instalación o indicar la ruta real.

## 2. Verificar pgAdmin 4

Abrir pgAdmin 4 y comprobar que inicia correctamente.

La contraseña maestra de pgAdmin no debe compartirse con Claude.

## 3. Registrar el servidor PostgreSQL en pgAdmin

En pgAdmin:

1. Servers → Register → Server.
2. `General > Name`: `ERP SaaS Local`.
3. `Connection > Host`: el host real detectado, normalmente `127.0.0.1`.
4. `Connection > Port`: el puerto real detectado, normalmente `5432`.
5. `Maintenance database`: normalmente `postgres`.
6. Usuario: el usuario PostgreSQL real.
7. Contraseña: introducirla en pgAdmin, no compartirla en el chat.
8. Save.

Claude debe decirte qué valores usar basándose en la detección local; no debe inventar rutas, puertos o usuarios.

## 4. Crear la base de datos del proyecto

En pgAdmin:

1. Servers → PostgreSQL → Databases.
2. Click derecho → Create → Database.
3. Nombre recomendado: `erp_saas_dev`.
4. Owner: usuario de aplicación PostgreSQL.
5. Save.

Claude puede crear esta base por CLI/SQL cuando tenga acceso, y luego usar pgAdmin para verificar. No hace falta crearla manualmente si Claude puede hacerlo de forma segura.

## 5. Crear usuario de aplicación

Preferir un usuario PostgreSQL dedicado para Django.

Claude debe crear y configurar el usuario cuando pueda. Si debe elegir una contraseña personal, pedirá al usuario que la introduzca de forma segura.

## 6. Configurar variables de entorno

Crear `.env` a partir de `.env.example`.

Ejemplo conceptual:

```env
DB_ENGINE=django.db.backends.postgresql
DB_NAME=erp_saas_dev
DB_USER=erp_saas_app
DB_PASSWORD=***
DB_HOST=127.0.0.1
DB_PORT=5432
```

Nunca subir `.env` a Git.

## 7. Configurar Django

Django debe usar PostgreSQL desde el inicio. No usar SQLite para la aplicación principal salvo como herramienta temporal de una prueba explícita.

## 8. Probar la conexión

Claude ejecutará:

```powershell
python manage.py check
python manage.py migrate
```

También debe ejecutar una comprobación de conexión desde Django si es necesario.

## 9. Verificar en pgAdmin

Después de migrar:

1. Refresh sobre `erp_saas_dev`.
2. Schemas → public → Tables.
3. Confirmar tablas Django.
4. Confirmar que los datos aparecen en la base correcta.

## 10. ¿Se integra automáticamente?

No completamente. Claude puede crear archivos, instalar dependencias, crear la base de datos y configurar Django si dispone de acceso al terminal y permisos. Sin embargo, pgAdmin 4 es una aplicación gráfica local y algunas contraseñas o confirmaciones pueden requerir interacción tuya. Por eso Claude debe conducirte paso a paso y detenerse únicamente cuando necesite una acción que solo tú puedas realizar.

## 11. Regla de verificación

No avanzar a la siguiente fase hasta que:

- PostgreSQL esté accesible.
- Django se conecte correctamente.
- Las migraciones funcionen.
- pgAdmin muestre las tablas esperadas.
- Los tests de conexión pasen.
