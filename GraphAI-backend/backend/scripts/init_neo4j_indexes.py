"""
Neo4j 索引初始化脚本
用于在应用启动前创建 Graphiti 所需的所有索引
"""
import os
import sys
import time
from neo4j import GraphDatabase
from neo4j.exceptions import ServiceUnavailable, AuthError

def get_neo4j_config():
    """从环境变量获取 Neo4j 配置"""
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    username = os.getenv("NEO4J_USERNAME", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "")
    if not password:
        raise ValueError("NEO4J_PASSWORD 环境变量未设置")
    return uri, username, password

def wait_for_neo4j(driver, max_retries=30, retry_interval=2):
    """等待 Neo4j 就绪"""
    print(f"⏳ 等待 Neo4j 服务就绪...")
    for i in range(max_retries):
        try:
            with driver.session() as session:
                session.run("RETURN 1")
            print(f"✅ Neo4j 服务已就绪")
            return True
        except (ServiceUnavailable, AuthError) as e:
            if i < max_retries - 1:
                print(f"⚠️  尝试 {i+1}/{max_retries}: Neo4j 未就绪，{retry_interval}秒后重试... ({e})")
                time.sleep(retry_interval)
            else:
                print(f"❌ Neo4j 服务在 {max_retries * retry_interval} 秒后仍未就绪")
                return False
    return False

def create_indexes(driver):
    """创建 Graphiti 所需的所有索引"""
    indexes = [
        # Entity 节点索引
        "CREATE INDEX entity_uuid IF NOT EXISTS FOR (n:Entity) ON (n.uuid)",
        "CREATE INDEX entity_group_id IF NOT EXISTS FOR (n:Entity) ON (n.group_id)",
        "CREATE INDEX name_entity_index IF NOT EXISTS FOR (n:Entity) ON (n.name)",
        "CREATE INDEX created_at_entity_index IF NOT EXISTS FOR (n:Entity) ON (n.created_at)",
        
        # Episodic 节点索引
        "CREATE INDEX episode_uuid IF NOT EXISTS FOR (n:Episodic) ON (n.uuid)",
        "CREATE INDEX episode_group_id IF NOT EXISTS FOR (n:Episodic) ON (n.group_id)",
        "CREATE INDEX created_at_episodic_index IF NOT EXISTS FOR (n:Episodic) ON (n.created_at)",
        "CREATE INDEX valid_at_episodic_index IF NOT EXISTS FOR (n:Episodic) ON (n.valid_at)",
        
        # Community 节点索引
        "CREATE INDEX community_uuid IF NOT EXISTS FOR (n:Community) ON (n.uuid)",
        "CREATE INDEX community_group_id IF NOT EXISTS FOR (n:Community) ON (n.group_id)",
        
        # RELATES_TO 关系索引
        "CREATE INDEX relation_uuid IF NOT EXISTS FOR ()-[e:RELATES_TO]-() ON (e.uuid)",
        "CREATE INDEX relation_group_id IF NOT EXISTS FOR ()-[e:RELATES_TO]-() ON (e.group_id)",
        "CREATE INDEX name_edge_index IF NOT EXISTS FOR ()-[e:RELATES_TO]-() ON (e.name)",
        "CREATE INDEX created_at_edge_index IF NOT EXISTS FOR ()-[e:RELATES_TO]-() ON (e.created_at)",
        "CREATE INDEX expired_at_edge_index IF NOT EXISTS FOR ()-[e:RELATES_TO]-() ON (e.expired_at)",
        "CREATE INDEX valid_at_edge_index IF NOT EXISTS FOR ()-[e:RELATES_TO]-() ON (e.valid_at)",
        "CREATE INDEX invalid_at_edge_index IF NOT EXISTS FOR ()-[e:RELATES_TO]-() ON (e.invalid_at)",
        
        # MENTIONS 关系索引
        "CREATE INDEX mention_uuid IF NOT EXISTS FOR ()-[e:MENTIONS]-() ON (e.uuid)",
        "CREATE INDEX mention_group_id IF NOT EXISTS FOR ()-[e:MENTIONS]-() ON (e.group_id)",
        
        # HAS_MEMBER 关系索引
        "CREATE INDEX has_member_uuid IF NOT EXISTS FOR ()-[e:HAS_MEMBER]-() ON (e.uuid)",
        
        # 全文索引
        "CREATE FULLTEXT INDEX episode_content IF NOT EXISTS FOR (e:Episodic) ON EACH [e.content, e.source, e.source_description, e.group_id]",
        "CREATE FULLTEXT INDEX node_name_and_summary IF NOT EXISTS FOR (n:Entity) ON EACH [n.name, n.summary, n.group_id]",
        "CREATE FULLTEXT INDEX community_name IF NOT EXISTS FOR (n:Community) ON EACH [n.name, n.group_id]",
        "CREATE FULLTEXT INDEX edge_name_and_fact IF NOT EXISTS FOR ()-[e:RELATES_TO]-() ON EACH [e.name, e.fact, e.group_id]",
    ]
    
    print(f"📊 开始创建 {len(indexes)} 个索引...")
    created_count = 0
    skipped_count = 0
    
    with driver.session() as session:
        for idx_query in indexes:
            try:
                result = session.run(idx_query)
                summary = result.consume()
                
                # 检查索引是否已存在
                if summary.counters.indexes_added > 0:
                    created_count += 1
                    print(f"  ✅ 创建: {idx_query[:80]}...")
                else:
                    skipped_count += 1
                    print(f"  ⏭️  已存在: {idx_query[:80]}...")
                    
            except Exception as e:
                print(f"  ⚠️  失败: {idx_query[:80]}... ({e})")
    
    print(f"\n✅ 索引初始化完成: 创建 {created_count} 个, 跳过 {skipped_count} 个")
    return True

def main():
    """主函数"""
    print("=" * 80)
    print("🚀 Neo4j 索引初始化脚本")
    print("=" * 80)
    
    # 获取配置
    uri, username, password = get_neo4j_config()
    print(f"📡 Neo4j URI: {uri}")
    print(f"👤 用户名: {username}")
    
    # 创建驱动
    try:
        driver = GraphDatabase.driver(uri, auth=(username, password))
    except Exception as e:
        print(f"❌ 无法创建 Neo4j 驱动: {e}")
        sys.exit(1)
    
    try:
        # 等待 Neo4j 就绪
        if not wait_for_neo4j(driver):
            print("❌ Neo4j 服务未就绪，退出")
            sys.exit(1)
        
        # 创建索引
        if not create_indexes(driver):
            print("❌ 索引创建失败")
            sys.exit(1)
        
        print("\n" + "=" * 80)
        print("🎉 Neo4j 初始化成功！")
        print("=" * 80)
        sys.exit(0)
        
    except Exception as e:
        print(f"\n❌ 初始化过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        driver.close()

if __name__ == "__main__":
    main()
