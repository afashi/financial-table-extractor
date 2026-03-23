# 财务年报复杂表格提取系统 - 核心技术设计方案

本方案旨在构建一套工业级的、专门针对财务年报（PDF）中复杂非结构化表格进行数据提取的系统。针对财务数据“零容错”的特性，系统采用 **“计算与业务分离”** 的微服务架构，并在核心算法上遵循 **“规则优先，模型兜底（Rule-First, Model-Fallback）”** 策略。

## 1. 系统整体架构概览

本系统采用 **“生产者-消费者”异步消息驱动微服务架构**。为了最大化算力利用率，系统在物理层面进行了严格的“计算与业务分离”：

- **GPU 计算集群 (单一职责)**：仅部署高显存消耗的 **深度文档解析引擎**。作为纯粹的消费者，它静默地从队列拉取 PDF 任务，利用 MinerU 榨取 GPU 算力执行版面分析与表格识别，并输出结构化解析产物。
    
- **CPU 业务集群 (大脑与中枢)**：承载除底层文档解析外的 **所有业务与控制逻辑**。包括 API 网关接入、任务调度分发、基于 `pgvector` 的语义路由匹配、Pandas 规则提取、调用外部大模型接口（llmClient）进行兜底处理、单位/币种归一化、置信度计算以及前端可视化溯源服务等。
    
- **存储与状态中枢**：以 PostgreSQL (业务与向量数据) 和 MinIO (文件对象) 为底座，Redis 作为高速消息队列串联两套集群。
    

## 2. 技术栈选型矩阵

技术选型全面对齐业界主流标准，确保兼顾性能、生态与金融级稳定性。

|领域层级| 技术选型与推荐版本                                 |选型理由与架构契合度分析|
|---|-------------------------------------------|---|
|**基础环境与包管理**| **Python 3.12+**<br><br>**uv 0.10.x**     |Python 3.12+ 提供了更优的性能和更完善的类型提示。`uv` 是极速 Python 包管理器，大幅提升生产环境构建与依赖解析速度。|
|**前端展现与交互**| **Vue 3**<br><br>Vite + TailwindCSS       |业界主流现代前端栈。结合自定义的 PDF Canvas 渲染层，支撑左侧数据表单与右侧 PDF BBox 的“所见即所得”高亮联动。|
|**核心业务服务 (CPU)**| **FastAPI 0.135+**<br><br>**Celery 5.6+** |**FastAPI** 是高性能异步框架，原生支持数据模型校验；**Celery** 作为工业级分布式队列，稳定调度横跨 CPU/GPU 的复杂处理链路。|
|**数据处理引擎**| **Pandas 3.0.x**<br><br>**Pydantic 2.x**  |**Pandas 3.0** 是执行行列切割、跨页拼接的利器；**Pydantic V2** 基于 Rust 重写，以极快速度对大模型返回的 JSON Schema 进行严格校验。|
|**智能解析服务 (GPU)**| **MinerU (Magic-PDF) 2.7.x**              |开源 SOTA 级的版面分析与表格结构识别引擎，精准输出包含页面坐标 (BBox) 等元数据的解析产物。|
|**向量检索与轻量模型**| **BAAI/bge-m3**                     |顶尖中文语义表征轻量模型，在 CPU 节点即可高效运行推理，完美满足“锚点库”精排打分需求。|
|**大模型兜底网关**| **LiteLLM / llmClient**                   |允许以统一的标准格式调用市面主流外部大模型 API，实现随时、无缝切换模型供应商，业务代码零侵入。|
|**关系型与向量存储**| **PostgreSQL 18.x**<br><br>**pgvector** 插件 |核心基石。原生支持强一致性事务；`JSONB` 完美适配非标表格存储；`pgvector` 提供向量索引，直接在 DB 层完成语义定位。|
|**异步消息与缓存**| **Redis 8.4+**                            |承担系统的消息队列总线与热点缓存。轻量、极速，与 Celery 深度集成。|
|**对象存储**| **MinIO**                                 |私有化 S3 标准存储池，低成本存放 PDF 原件及庞大的解析产物。|

## 3. 功能模块拆分与职责边界

系统划分为以下子模块，严格遵循“高内聚、低耦合”原则：

### 3.1 部署于 GPU 集群的模块

- **深度文档解析引擎 (GPU Parser Engine)**
    
    - **唯一职责**：独立部署的微服务。监听队列，从 MinIO 获取 PDF 文件，调用 MinerU 引擎执行高耗时的 OCR、版面还原与表格识别，将携带严格物理坐标（BBox）的解析产物落盘至 MinIO，并向 CPU 集群发送“解析完成”事件。
        

### 3.2 部署于 CPU 集群的模块

- **网关与任务调度模块 (API & Task Dispatcher)**
    
    - **职责**：系统统一入口。负责参数校验、生成任务批次号、将解析任务投递至 Redis 队列，并提供符合 RESTful 规范的任务状态查询接口。
        
- **语义路由与智能提取模块 (Semantic Routing & Extraction Pipeline)**
    
    - **职责**：执行多步核心逻辑。包含跨页长表格合并处理；基于文档目录树与“路径指纹库”的宏观比对降维；结合轻量级向量模型与 `pgvector` 进行“锚点”微观语义定位；并在成功锁定标准表后，利用 Pandas 依据坐标系进行高速行列提取。
        
- **泛化模型兜底网关 (LLM Fallback Client)**
    
    - **职责**：当且仅当“定位到章节但未找到标准表格”时触发。动态组装文本碎片作为上下文，通过 `llmClient` 请求外部大语言模型，通过 Prompt 强制约束模型输出预定义的 JSON 数据或 `"NOT_DISCLOSED"` 状态。
        
- **规则转换与后处理中心 (Transformation Engine)**
    
    - **职责**：执行数据的“最后一公里”清洗。智能识别并绑定“单位/币种”；执行严格的财务语义转换（区分 `0.00`, `null`, `"NOT_DISCLOSED"`）；通过策略注册机制，运行针对特定异常表格的 Python 清洗脚本（如行列转置、多级表头展平）。
        
- **全局置信度与审计模块 (Confidence & Audit Subsystem)**
    
    - **职责**：基于向量匹配精度损耗、大模型降级触发、元数据缺失等维度，为每条提取出的数据计算置信度得分。自动拦截低分数据并推入待办复核队列。
        
- **溯源与可视化后端服务 (Traceability Backend)**
    
    - **职责**：响应前端展现模块的请求，提供精确映射的数据与物理坐标（BBox）联动接口，支撑前端在 PDF 容器中绘制高亮溯源框。
        

## 4. 核心数据流转机制设计

本节详细定义了从用户发起解析请求到最终结构化数据落盘的端到端数据流转链路。系统以 `TaskID` 为生命周期主键，通过 Redis 消息队列驱动任务在 CPU 与 GPU 之间异步流转。

### 4.1 主流程阶段化数据流转明细 (Data Flow Details)

系统以 Celery Task 为承载体，严格约束每个节点的 `Input` 和 `Output`。

#### Phase 0: 任务接入与调度分发

- **触发器**: 前端发起 `POST /api/v1/extract` 请求。
    
- **处理逻辑 (CPU)**:
    
    1. 明确规定前端传入 doc_type 参数（区分财务报告、招股说明书、债券报告等）
    2. 指纹提取: 读取上传的 PDF 字节流，计算文件的 SHA-256 哈希值以及 file_size（文件字节大小）。
    3. 去重校验 (DB 查询): 在 PostgreSQL 的 tasks 表中查询是否存在相同的 file_hash、file_size 且 doc_type 一致的记录。
    4. 命中已有文件，执行 SQL 更新，将该条记录的 updated_time 字段更新为当前最新时间（NOW()）。不再将任务推入任何队列，也不重复上传 MinIO，结束流程。
    5. 若没有命中文件，生成全局唯一 `TaskID`。
    6. 将上传的 PDF 字节流异步写入 MinIO（路径: `tasks/{TaskID}/source/{FileName}`）。
    7. 在 PostgreSQL `tasks` 表初始化记录，状态设为 `QUEUED`。
    8. 将携带 `task_id` 与源文件对象存储引用的解析请求压入 Redis 的 `parser_queue`。
        
- **状态变更**: `QUEUED`
    

#### Phase 1: 高精度版面解析 (GPU 单向流转)

- **触发器**: GPU Worker 监听到 `parser_queue` 消息。
    
- **处理逻辑 (GPU)**:
    
    1. 从 MinIO 拉取 PDF 文件到 GPU 节点显存/本地盘，并向 CPU 集群发送 `ParseStarted` 事件。
        
    2. 运行 MinerU 进行版面分析、公式识别、表格还原。
        
    3. 生成核心产物 `content_list.json`，表格切片图片（可选）。
        
    4. 将 `content_list.json` 传回 MinIO（路径: `tasks/{TaskID}/content_list.json`），表格切片图片传回 MinIO（路径: `tasks/{TaskID}/slices/page-{n}.png`）。`content_list.json` 作为 canonical parse artifact 只读保存，后续阶段只消费不回写。
        
    5. 若解析成功且产物校验通过，则向 CPU 集群发送 `ParseCompleted` 事件；若解析失败或产物校验不通过，则发送 `ParseFailed` 事件并写入失败原因。
        
- **状态变更**: `QUEUED` -> `PARSING` -> `PARSED`；失败路径为 `PARSING` -> `FAILED`
    

#### Phase 2: 数据预处理与跨页合并

- **触发器**: CPU Core Worker 监听到 `extractor_queue` 消息。
    
- **输入**: 从 MinIO 加载 `content_list.json` 至内存字典。
    
- **流转动作**:
    
    - **识别**: 遍历所有表格节点，检测相邻页面是否存在连贯表格（判断依据：表头结构完全一致、带有“续表”字样等）。
        
    - **合并**: 动态生成 `continue_table_id`，利用 `Pandas.concat` 对属于同一逻辑表的切片进行纵向拼接，并静默剥离后续页的重复表头。
        
- **输出**: 内存态的逻辑宽长表列表 `List[LogicalTable]`。
    

#### Phase 3: 语义路由与智能双路提取 (核心路由节点)

本阶段是系统分流的“十字路口”。

- **动作 1：宏观路由降维**
    
    - 系统读取 `content_list.json` 中的层级标题树 (TOC) 与对应的物理页码/BBox，并且保存到另一张表中。
        
    - 比对 PG 数据库中的“路径指纹库”，将全量文档过滤至目标章节（如锁定“主营业务分析”章节的 BBox 范围）。
        
- **动作 2：多策略微观锚点匹配 (Multi-Strategy Anchoring) 【核心升级】**

- 系统遍历目标章节内的候选表格及其上下文，读取数据库中预设的“锚点规则库”（存储为 JSONB 格式的复合规则集），执行优先级级的降维匹配机制：
    
    1. **逻辑/符号匹配 (Logic & Text Match)**: 极低算力消耗，最高绝对优先级。校验表头、标题或上下文是否满足绝对条件。
        
    2. **正则提取匹配 (Regex Match)**: 用于应对带有动态年份或略微变体的非标名称（例如：匹配标题正则 `^202[0-9]年度.*主营业务分部.*$`）。
        
    3. **向量语义匹配 (Vector Semantic Match)**: 当上述硬规则未能 100% 锁定唯一表格，或作为综合打分的补充时，将文本通过 `BAAI/bge-m3` 转化为向量，通过 `pgvector` 计算上下文的余弦相似度。
        
- **路由决策分发机制 (Router Decision)**:
    
    - **Condition A (匹配度 > 表格识别规则配置的最小匹配度)**: 判定为标准表，进入 **[规则快车道]**。利用 Pandas 结合 BBox 进行精确的行列裁剪提取。
        
    - **Condition B (未找到表，但匹配到了所在章节)**: 触发 **[大模型慢车道]**。将该章节范围内的文本块（Text Blocks）和破裂表格碎片拼接拼接为一段完整的 Context，注入到 `llmClient` 的 Prompt 中，强制要求输出结构化 JSON，若无数据则输出 `"NOT_DISCLOSED"`。
        
    - **Condition C (全文未找到目标模块)**: 直接终止该指标的提取，标记结果为 `"NOT_FIND"`。
        

#### Phase 4: 归一化与可插拔策略后处理

- **输入**: 经过 Phase 3 提取的粗粒度结构化数据 (JSON / DataFrame) 及所在区域的 BBox。
    
- **流转动作**:
    
    1. **元数据嗅探**: 基于定位到的目标表格，向上扫描临近的文本块，使用正则/NER提取金额单位和币种。
        
    2. **强制归一化**: 将单位映射为系统枚举值（如提取到“人民币万元” -> `CNY_TEN_THOUSAND`），强绑定至数据行。
        
    3. **精确语义转换**: 扫描单元格内容，执行“零容错”映射。将 `-` 或空白映射为 `null`；将明确的 `0` 映射为 `0.00`。
        
    4. **策略引擎拦截**: 根据当前提取的 `[表格业务类型]`，在引擎中查找是否注册了定制化的 Python 后处理脚本（如多级表头展平策略）。若命中，则将数据传入该脚本处理后返回。
        

#### Phase 5: 全局置信度评分体系计分与数据落盘

- **流转动作**:
    
    - 系统为最终生成的数据结构计算 `confidence_score` (基础 100 分。向量匹配度0.85-0.9损耗扣 5 分；走大模型慢车道扣 15 分；单位无法确定触发默认值扣 10 分)。
        
    - 将携带 BBox 和置信度分的最终 JSONB 数据持久化到 PostgreSQL。
        
- **状态判断**:
    
    - 若所有指标 `confidence_score >= 85` -> 状态更新为 `COMPLETED`。
        
    - 若存在指标 `confidence_score < 85` -> 状态更新为 `PENDING_REVIEW`，推入前端人工复核队列。

#### Phase 6: 数据溯源与“所见即所得”可视化核对 

本阶段是系统数据交付的最后一环，通过 BBox 坐标映射实现数据的 100% 可解释与可追溯，支撑最终的人工复核闭环。

- **触发器**: 任务数据落盘完毕，状态变更为 `COMPLETED` 或 `PENDING_REVIEW`。
    
- **流转与交互动作**:
    
    1. **视图加载**: 前端调用“溯源与可视化后端服务”，获取结构化数据与 PDF 切片，渲染“左侧表格/表单，右侧 PDF 预览”的双栏核对界面。
        
    2. **坐标联动**: 依托底层引擎解析并一路透传的 `bbox` 物理坐标数据，前端建立数据与文档位置的精准映射。
        
    3. **溯源高亮**: 当用户在左侧点击任意表格或数据行时，右侧 PDF 自动翻页跳转至对应位置，并利用 BBox 坐标绘制高亮红框，精准圈出原始出处。
        
- **结果**: 完成人机协同闭环。审计人员基于高亮区域即可实现“一眼定真伪”，快速完成异常数据的核对与状态确认。

### 4.2 其他流程

#### 4.2.1 中间阶段局部重跑机制 (基于 Phase 3 的指定表格重触发)

针对前端人工复核环节或提取规则（正则/锚点）发生热更新的场景，系统支持跳过高耗时的 GPU 物理版面解析（Phase 1）与全局跨页合并（Phase 2），直接从 Phase 3 针对特定表格重新发起提取链路。

- **触发器**: 前端或内部调度脚本发起 `POST /api/v1/extract/retrigger` 请求，Payload 携带特定的 `TaskID`、指定的 `TargetTableIDs`。
    
- **处理逻辑 (CPU Core Worker)**:
    
    1. **指令接收与旁路校验**: API 网关接收指令后，校验 PostgreSQL 中该 `TaskID` 的有效性。不再生成新任务，而是将带有局部参数的重跑消息压入 Redis 的专属队列（如 `re_extractor_queue`）。
        
    2. **局部状态恢复 (跳过 Phase 1 & 2)**: CPU Worker 监听到消息后，直接从 MinIO 加载现存的 `content_list.json` 到内存中。不再执行全局遍历，而是根据传入的 `TargetTableIDs` 或 BBox 精准裁切出目标表格及其上下文（Context）。
        
    3. **定向语义路由与提取 (Phase 3 局部覆写)**:
        
        - 针对被选中的表格，重新执行多策略微观锚点匹配。
                        
    4. **局部后处理清洗 (执行 Phase 4)**: 对重新提取出来的数据片，照常执行单位嗅探、强绑定与可插拔策略脚本的清洗转换。
        
    5. **局部计分与状态合并 (执行 Phase 5)**:
        
        - 重新计算该指定表格的 `confidence_score`。
            
        - 采用“局部 Upsert”策略更新 PostgreSQL 中对应的数据行，保留其他未重跑表格的既有数据。
            
- **状态变更评估**: 局部落盘后，系统重新评估该 `TaskID` 的全局状态。若原状态为 `PENDING_REVIEW`，且本次重跑后所有指标的 `confidence_score` 均已 `>= 85`，系统将自动把该任务状态翻转为 `COMPLETED`。

## 5. 离线配置与产物格式（rule.json / extracted_result.json）

本节定义与 `content_list.json` 配套的规则库输入与最终提取产物的 JSON 结构，便于离线调试与链路回归。

### 5.1 rule.json（规则库）

**字段说明**
- `doc_type`: 文档类型（如 `ANNUAL_REPORT`、`IPO_PROSPECTUS`）。
- `rules`: 规则列表。
- `rules[].target_table_code`: 目标指标代码（如 `main_business_revenue`）。
- `rules[].target_table_name`: 目标表格名称（人类可读）。
- `rules[].path_fingerprints`: 章节路径指纹数组（用于宏观路由降维）。
- `rules[].anchor_rule`: 微观锚点规则对象（逻辑/正则等组合规则）。
- `rules[].anchor_rule.logic_match.required_headers`: 必须包含的表头列名数组。
- `rules[].anchor_rule.logic_match.required_context_keywords`: 上下文必须包含的关键词数组。
- `rules[].anchor_rule.regex_match.title_pattern`: 表格标题正则（用于年份/变体匹配）。
- `rules[].semantic_anchor_text`: 向量语义锚点原始文本。
- `rules[].min_match_score`: 最低语义相似度阈值（0-1）。
- `rules[].is_active`: 启用状态（`"1"` 启用，`"0"` 停用）。

**示例**
```json
{
  "doc_type": "ANNUAL_REPORT",
  "rules": [
    {
      "target_table_code": "main_business_revenue",
      "target_table_name": "主营业务分部收入",
      "path_fingerprints": ["管理层讨论与分析", "主营业务分析"],
      "anchor_rule": {
        "logic_match": {
          "required_headers": ["分部", "营业收入", "毛利率"],
          "required_context_keywords": ["主营业务", "分部"]
        },
        "regex_match": {
          "title_pattern": "^202[0-9]年度.*主营业务分部.*$"
        }
      },
      "semantic_anchor_text": "主营业务分部收入表，包含分部、营业收入、毛利率等字段",
      "min_match_score": 0.88,
      "is_active": "1"
    }
  ]
}
```

### 5.2 extracted_result.json（最终提取产物）

**字段说明**
- `task_id`: 任务 ID（与 `t_task.id` 对应）。
- `doc_type`: 文档类型。
- `status`: 任务级状态（`COMPLETED` / `PENDING_REVIEW`）。
- `generated_at`: 产出时间（ISO 8601）。
- `results`: 提取结果列表。
- `results[].target_table_code`: 目标指标代码。
- `results[].target_table_name`: 目标表格名称。
- `results[].data_status`: `SUCCESS` / `NOT_DISCLOSED` / `NOT_FIND`。
- `results[].extraction_route`: `FAST_TRACK` / `SLOW_TRACK`（`NOT_FIND` 可为空）。
- `results[].unit`: 归一化单位（如 `CNY_TEN_THOUSAND`）。
- `results[].currency`: 币种（如 `CNY`）。
- `results[].confidence_score`: 置信度分数（0-100）。
- `results[].needs_review`: 是否需要复核（`"1"`/`"0"`）。
- `results[].start_page`: 表格起始物理页码。
- `results[].end_page`: 表格结束物理页码。
- `results[].bbox`: 表格级 BBox（多页可为数组）。
- `results[].table_data`: 结构化数据内容。
- `results[].fix_table_data`: 人工复核修复后的数据内容（可为空）。
- `results[].remark`: 备注信息（可为空）。

**示例**
```json
{
  "task_id": 102400001,
  "doc_type": "ANNUAL_REPORT",
  "status": "COMPLETED",
  "generated_at": "2026-03-16T12:00:00+08:00",
  "results": [
    {
      "target_table_code": "main_business_revenue",
      "target_table_name": "主营业务分部收入",
      "data_status": "SUCCESS",
      "extraction_route": "FAST_TRACK",
      "unit": "CNY_TEN_THOUSAND",
      "currency": "CNY",
      "confidence_score": 93.5,
      "needs_review": "0",
      "start_page": 85,
      "end_page": 86,
      "bbox": [
        {"page": 85, "x0": 68.2, "y0": 112.5, "x1": 540.3, "y1": 712.4},
        {"page": 86, "x0": 68.0, "y0": 90.1, "x1": 540.1, "y1": 688.9}
      ],
      "table_data": {
        "headers": ["分部", "营业收入", "毛利率"],
        "rows": [
          ["华东", "12345.67", "24.8%"],
          ["华南", "9876.54", "22.1%"]
        ]
      },
      "fix_table_data": null,
      "remark": null
    }
  ]
}
```
