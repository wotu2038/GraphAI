"""
MySQL数据库连接客户端
"""
from sqlalchemy import create_engine, MetaData, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# 构建MySQL连接URL（不指定数据库，用于创建数据库）
MYSQL_SERVER_URL = f"mysql+pymysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}?charset=utf8mb4"

# 构建MySQL连接URL（指定数据库）
MYSQL_URL = f"mysql+pymysql://{settings.MYSQL_USER}:{settings.MYSQL_PASSWORD}@{settings.MYSQL_HOST}:{settings.MYSQL_PORT}/{settings.MYSQL_DATABASE}?charset=utf8mb4"

# 创建数据库引擎
engine = create_engine(
    MYSQL_URL,
    pool_pre_ping=True,  # 连接前检查连接是否有效
    pool_recycle=3600,    # 连接回收时间（秒）
    echo=False            # 是否打印SQL语句
)

# 创建会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 创建基础模型类
Base = declarative_base()

# 获取数据库会话
def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def ensure_database_exists():
    """确保数据库存在，如果不存在则创建
    
    注意：通常 MySQL 容器的 MYSQL_DATABASE 环境变量会在首次初始化时自动创建数据库。
    此函数作为备用方案，在数据库不存在时尝试创建。
    如果普通用户没有创建数据库的权限，此函数会失败，但不会影响后续的表创建操作。
    """
    try:
        # 先连接到 MySQL 服务器（不指定数据库）
        server_engine = create_engine(
            MYSQL_SERVER_URL,
            pool_pre_ping=True,
            pool_recycle=3600,
            echo=False
        )
        
        with server_engine.connect() as conn:
            # 检查数据库是否存在
            result = conn.execute(text(
                f"SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME = '{settings.MYSQL_DATABASE}'"
            ))
            if result.fetchone() is None:
                # 数据库不存在，尝试创建它
                logger.warning(f"数据库 {settings.MYSQL_DATABASE} 不存在，正在尝试创建...")
                try:
                    conn.execute(text(f"CREATE DATABASE IF NOT EXISTS `{settings.MYSQL_DATABASE}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci"))
                    conn.commit()
                    logger.info(f"✅ 数据库 {settings.MYSQL_DATABASE} 创建成功")
                except Exception as create_error:
                    # 如果创建失败（可能是权限问题），记录警告但继续执行
                    logger.warning(f"无法创建数据库（可能是权限问题）: {create_error}")
                    logger.warning("数据库应该由 MySQL 容器的 MYSQL_DATABASE 环境变量自动创建")
            else:
                logger.debug(f"数据库 {settings.MYSQL_DATABASE} 已存在")
        
        server_engine.dispose()
    except Exception as e:
        logger.warning(f"检查数据库时出错（可能数据库尚未初始化）: {e}")
        # 如果检查失败，继续执行，让后续的错误处理来处理
        # 数据库可能正在初始化中，或者由 MySQL 容器自动创建

# 初始化数据库表
def init_db():
    """初始化数据库表"""
    # 首先确保数据库存在
    try:
        ensure_database_exists()
    except Exception as e:
        logger.error(f"无法确保数据库存在: {e}")
        # 如果数据库创建失败，尝试继续（可能是权限问题，数据库可能已存在）
    
    # 确保所有模型都被导入，这样它们才会注册到 Base.metadata 中
    # 注意：必须在 create_all 之前导入所有模型
    try:
        from app.models import (
            TaskQueue, DocumentUpload, EntityEdgeTemplate,
            KnowledgeBase, KnowledgeBaseMember, document_knowledge_base_association,
            User, DocumentLibrary, DocumentFolder, ChatHistory
        )
        logger.debug("所有模型已导入")
    except ImportError as e:
        logger.warning(f"导入模型时出现警告: {e}")
    
    # 创建所有表
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("MySQL数据库表初始化完成")
    except Exception as e:
        logger.error(f"创建数据库表时出错: {e}")
        raise

