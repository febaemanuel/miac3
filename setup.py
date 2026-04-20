"""Setup interativo do MIAC: gera .env, instala dependências e inicializa o banco."""
import os
import secrets
import subprocess
import sys


def perguntar(msg, padrao=""):
    resposta = input(f"{msg} [{padrao}]: ").strip() if padrao else input(f"{msg}: ").strip()
    return resposta or padrao


def criar_env():
    if os.path.exists(".env"):
        sobrescrever = input(".env já existe. Sobrescrever? (s/N): ").strip().lower()
        if sobrescrever != "s":
            print("Mantendo .env existente.")
            return

    print("\n--- Banco de dados (PostgreSQL) ---")
    host = perguntar("Host", "localhost")
    port = perguntar("Porta", "5432")
    user = perguntar("Usuário do banco")
    password = perguntar("Senha do banco")
    dbname = perguntar("Nome do banco")

    print("\n--- Usuário admin inicial ---")
    admin_user = perguntar("Username do admin", "admin")
    admin_senha = perguntar("Senha do admin", "admin")

    print("\n--- APIs de IA (opcional, Enter para pular) ---")
    deepseek = perguntar("DeepSeek API Key", "")
    openai = perguntar("OpenAI API Key", "")

    secret = secrets.token_hex(32)

    from werkzeug.security import generate_password_hash
    admin_hash = generate_password_hash(admin_senha)

    linhas = [
        f"SECRET_KEY={secret}",
        f"DB_HOST={host}",
        f"DB_PORT={port}",
        f"DB_USER={user}",
        f"DB_PASSWORD={password}",
        f"DB_NAME={dbname}",
        f"USER_ADMIN_USERNAME={admin_user}",
        f"USER_ADMIN_HASH={admin_hash}",
    ]
    if deepseek:
        linhas.append(f"DEEPSEEK_API_KEY={deepseek}")
    if openai:
        linhas.append(f"OPENAI_API_KEY={openai}")

    with open(".env", "w") as f:
        f.write("\n".join(linhas) + "\n")

    print(f"\n.env criado. Secret key gerada automaticamente.")


def instalar_deps():
    print("\n--- Instalando dependências ---")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"])


def criar_diretorios():
    dirs = [
        os.path.join("static", "uploads2"),
        os.path.join("static", "branding"),
    ]
    for d in dirs:
        os.makedirs(d, exist_ok=True)
        print(f"  ✓ {d}")


def inicializar_banco():
    print("\n--- Inicializando banco de dados ---")
    from app import create_app
    app = create_app()
    with app.app_context():
        from app.extensions import db
        db.create_all()
        from app.seed import run_seeds
        run_seeds()
    print("  ✓ Tabelas criadas e dados iniciais inseridos.")


def main():
    print("=" * 50)
    print("       Setup MIAC — Configuração inicial")
    print("=" * 50)

    criar_env()

    instalar = input("\nInstalar dependências do requirements.txt? (S/n): ").strip().lower()
    if instalar != "n":
        instalar_deps()

    print("\n--- Criando diretórios necessários ---")
    criar_diretorios()

    init_db = input("\nInicializar banco de dados agora? (S/n): ").strip().lower()
    if init_db != "n":
        inicializar_banco()

    print("\n" + "=" * 50)
    print("Setup concluído! Para rodar:")
    print("  python novo2.py")
    print("Acesse: http://localhost:8090/miac/login")
    print("=" * 50)


if __name__ == "__main__":
    import traceback
    try:
        main()
    except Exception:
        print("\n" + "=" * 50)
        print("ERRO durante o setup:")
        print("=" * 50)
        traceback.print_exc()
        print("=" * 50)
    finally:
        input("\nPressione Enter para sair...")
