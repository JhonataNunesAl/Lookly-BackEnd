from schemas.usuario import UsuarioCreate, UsuarioLogin
from core.security import create_access_token, revoke_token, get_password_hash, verify_password
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from model.usuario_model import Usuario 

async def cadastrar(dados: UsuarioCreate, db: AsyncSession):
    # 1. Verificar se o usuário já existe
    query = select(Usuario).where(Usuario.email == dados.email)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="E-mail já cadastrado"
        )

    # 2. Criar hash da senha
    hashed_password = get_password_hash(dados.senha)

    # 3. Salvar no banco
    novo_usuario = Usuario(
        nome=dados.nome,
        email=dados.email,
        senha=hashed_password,
        estilos=dados.estilos
    )
    
    db.add(novo_usuario)
    await db.commit()
    await db.refresh(novo_usuario)
    
    return novo_usuario


async def login(dados: UsuarioLogin, db: AsyncSession):
    
    query = select(Usuario).where(Usuario.email == dados.email)
    result = await db.execute(query)
    
    usuario = result.scalar_one_or_none()
    if not usuario or not verify_password(dados.senha, usuario.senha):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="E-mail ou senha inválidos"
        )
    token_data = {"sub": str(usuario.id), "nome": usuario.nome}
    access_token = create_access_token(token_data)
    return {"access_token": access_token, "token_type": "bearer"}

