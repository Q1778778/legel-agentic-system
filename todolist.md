* 除了case extraction外，其他都可以用通用的agent
* case extraction的话，可能需要和现在的graphrag或者neo4j（neo4j应该是备选的方案）然后去索引相对应的案例
* 然后legal Consulation，Opponent Analysis可以用通用的agent然后
* 然后需要用APIs: CourtListener, RECAP, Caselaw Access Project (CAP), GovInfo, eCFR, Oyez (optional), OpenStates
(optional)然后来开发获取最新的法律数据（可能需要和graphrag或者neo4j结合起来找到最好的，最匹配的）
* 确保系统绝对可用