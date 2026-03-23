**t_task**

|字段|类型|约束/默认值|备注|
|---|---|---|---|
|id|BIGINT|PK|雪花算法生成的全局唯一主键 (即 TaskID)|
|doc_type|VARCHAR(32)|NOT NULL|文档类型：区分财务报告、招股说明书等|
|file_name|VARCHAR(255)|NOT NULL|原始文件名|
|file_hash|VARCHAR(64)|NOT NULL|文件 SHA-256 哈希值 (用于去重)|
|file_size|BIGINT|NOT NULL|文件字节大小 (用于去重)|
|status|VARCHAR(32)|DEFAULT 'QUEUED'|状态: QUEUED, PARSING, PARSED, PENDING_REVIEW, COMPLETED, FAILED|
|remark|VARCHAR(512)|NULL|备注信息|
|create_time|TIMESTAMP WITH TIME ZONE|DEFAULT CURRENT_TIMESTAMP|创建时间|
|update_time|TIMESTAMP WITH TIME ZONE|DEFAULT CURRENT_TIMESTAMP|更新时间|

索引  
- `idx_t_task_hash_size_doc_type`：UNIQUE(`file_hash`, `file_size`, `doc_type`)

**t_document_toc**

|字段|类型|约束/默认值|备注|
|---|---|---|---|
|id|BIGINT|PK|雪花算法生成的全局唯一主键|
|task_id|BIGINT|NOT NULL|关联 t_task.id|
|level|INTEGER|NOT NULL|标题层级 (1, 2, 3...)|
|title|VARCHAR(512)|NOT NULL|标题内容 (例如："主营业务分析")|
|start_page|INTEGER|NOT NULL|章节起始物理页码|
|end_page|INTEGER|NOT NULL|章节结束物理页码|
|start_y|NUMERIC(10,4)|NULL|章节起始Y轴坐标|
|end_y|NUMERIC(10,4)|NULL|章节结束Y轴坐标|
|parent_id|BIGINT|NULL|树形自关联 (指向本表的 id)|
|create_time|TIMESTAMP WITH TIME ZONE|DEFAULT CURRENT_TIMESTAMP|创建时间|
|update_time|TIMESTAMP WITH TIME ZONE|DEFAULT CURRENT_TIMESTAMP|更新时间|

索引  
- `idx_t_document_toc_task`：(`task_id`)

**t_table_extraction_rule**

|字段|类型|约束/默认值|备注|
|---|---|---|---|
|id|BIGINT|PK|雪花算法生成的全局唯一主键|
|doc_type|VARCHAR(32)|NOT NULL|关联的文档类型|
|target_table_code|VARCHAR(64)|NOT NULL|目标指标代码 (如: main_business_revenue)|
|target_table_name|VARCHAR(128)|NOT NULL|目标表格名称|
|path_fingerprints|JSONB|NOT NULL|路径指纹库 (如: ["管理层讨论与分析", "主营业务分析"])|
|anchor_rule|JSONB|NULL|微观路由锚点规则综合字段 (整合逻辑、正则等规则)|
|semantic_anchor_text|VARCHAR(2000)|NULL|用于生成向量的原始锚点文本（限制长度替代 Text）|
|semantic_vector|vector(512)|NULL|锚点向量表示|
|min_match_score|NUMERIC(4,3)|NULL|最低余弦相似度阈值|
|is_active|VARCHAR(1)|DEFAULT '1'|启停状态：'0' 停用, '1' 启用|
|create_time|TIMESTAMP WITH TIME ZONE|DEFAULT CURRENT_TIMESTAMP|创建时间|
|update_time|TIMESTAMP WITH TIME ZONE|DEFAULT CURRENT_TIMESTAMP|更新时间|

索引  
- `idx_t_rule_doc_type_code`：UNIQUE(`doc_type`, `target_table_code`)  
- `idx_t_rule_vector`：HNSW(`semantic_vector` vector_cosine_ops)

**t_extracted_result**

|字段|类型|约束/默认值|备注|
|---|---|---|---|
|id|BIGINT|PK|雪花算法生成的全局唯一主键|
|task_id|BIGINT|NOT NULL|关联 t_task.id|
|rule_id|BIGINT|NOT NULL|关联 t_table_extraction_rule.id|
|target_table_code|VARCHAR(64)|NOT NULL|目标指标代码 (冗余字段，便于快速查询)|
|unit|VARCHAR(32)|NULL|智能提取并归一化的单位 (如: CNY_TEN_THOUSAND)|
|currency|VARCHAR(16)|NULL|币种|
|extraction_route|VARCHAR(32)|NULL|提取路径：FAST_TRACK, SLOW_TRACK（NOT_FIND 时可为空）|
|data_status|VARCHAR(32)|NOT NULL|最终语义: SUCCESS, NOT_DISCLOSED, NOT_FIND|
|table_data|JSONB|NULL|系统自动提取的核心数据内容|
|fix_table_data|JSONB|NULL|人工复核修复后的数据内容|
|start_page|INTEGER|NULL|表格起始物理页码|
|end_page|INTEGER|NULL|表格结束物理页码|
|bbox|JSONB|NULL|表格级 BBox 信息（如含多页，可存数组）|
|confidence_score|NUMERIC(5,2)|NOT NULL|0-100分，计算置信度得分|
|needs_review|VARCHAR(1)|NULL|是否需要复核：'0' 否, '1' 是 (可根据应用层逻辑结合 score 写入)|
|remark|VARCHAR(512)|NULL|备注信息|
|create_time|TIMESTAMP WITH TIME ZONE|DEFAULT CURRENT_TIMESTAMP|创建时间|
|update_time|TIMESTAMP WITH TIME ZONE|DEFAULT CURRENT_TIMESTAMP|更新时间|

索引  
- `idx_t_result_task`：(`task_id`)  
- `idx_t_result_review`：(`needs_review`) WHERE `needs_review` = '1'
