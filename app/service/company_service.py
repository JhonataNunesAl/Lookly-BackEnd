from schemas.usuario import UsuarioCreate, UsuarioLogin
from core.security import create_access_token, revoke_token, get_password_hash, verify_password
from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from model.company_model import Company


async def cadastrar(dados: UsuarioCreate, db: AsyncSession):
    # 1. Verificar se a empresa já existe
    query = select(Company).where(Company.email == dados.email)
    result = await db.execute(query)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Empresa já cadastrado"
        )

    # 2. Criar hash da senha
    hashed_password = get_password_hash(dados.senha)

    # 3. Salvar no banco
    nova_empresa = Company(
        nome=dados.nome,
        cnpj=dados.CNPJ,
        descricao=dados.descricao,
        segmento=dados.segmento,
        email=dados.email,
        logo=dados.logo,
        senha=hashed_password,
        estilos=dados.estilos
    )
    
    db.add(nova_empresa)
    await db.commit()
    await db.refresh(nova_empresa)
    
    return nova_empresa




async def login(dados: UsuarioLogin, db: AsyncSession):
    
    query = select(Company).where(Company.email == dados.email)
    result = await db.execute(query)
    
    empresa = result.scalar_one_or_none()
    if not empresa or not verify_password(dados.senha, empresa.senha):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, 
            detail="E-mail ou senha inválidos"
        )
    token_data = {"sub": str(empresa.id), "nome": empresa.nome}
    access_token = create_access_token(token_data)
    return {"access_token": access_token, "token_type": "bearer"}