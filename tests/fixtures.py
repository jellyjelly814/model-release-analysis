"""Synthetic Feishu fixtures. No credentials, live targets or network calls."""
import copy
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"scripts"))
from sync_common import utc_now, file_digest, invalidate


def manifest(directory,scope=None):
    scope=scope or ["A","B","C"]
    root=Path(directory);(root/"html").mkdir(exist_ok=True)
    (root/"html/source.txt").write_text("Fixture Model v1 released; fixture evidence only.")
    m={"schema_version":3,"run_id":"fixture-run","created_at":utc_now(),"mode":"feishu_sync","mutation_generation":0,
       "model_identity":{"company":"Fixture","name":"Fixture Model","version":"v1","release_date":"2026-09-11"},
       "evidence_policy":{"artificial_analysis":{"status":"checked_unavailable","checked_urls":["https://artificialanalysis.ai/models"],"reason":"synthetic fixture only","alternatives":["fixture release"]}},
       "sync_target":{"parent_doc":"parentDoc","parent_wiki_node":"parentWiki","vendor_heading":"Fixture Vendor","scope":scope,
                      "allowed_link_hosts":["fixture.feishu.cn"],"permission_preflight":{"identity":"user_access_token","status":"complete",
                      "docx_read":True,"docx_read_write":True,"media_read_write":True,"sheets_read_write":True,"wiki_node_manage":True}},
       "parent_section":{"wiki_node":"parentWiki","vendor":"Fixture Vendor","model_entry":"【2026/09/11】Fixture Model: audit","status":"pending"},
       "child_wiki_doc":{"parent_node":"parentWiki","parent_node_token":"parentWiki","node_token":"childWiki","obj_token":"childDoc",
                         "title":"【2026/09/11】Fixture Model: audit","operation":"update","status":"pending"},
       "table_inventory":[{"block_id":"sheetBlock","sheet_token":"spreadsheet_sheet1","relevant":True,"reason":"model pricing"}],
       "related_tables":[{"block_id":"sheetBlock","spreadsheet_token":"spreadsheet","sheet_id":"sheet1","model_column":"A",
                          "header_range":"A1:C1","header":["Model","Price","Total"],"reason":"fixture pricing", "action":"updated","status":"pending",
                          "model_keys":["Fixture v1"],"expected_occurrences":1,
                          "checks":[{"range":"A2:C2","expected_values":[["Fixture v1",2,4]],"expected_formulas":[[None,None,"=B2*2"]]}]}],
       "screenshots":[],"screenshot_candidates":[],"journal":[],"target_status":{"A":"pending","B":"pending","C":"pending"},
       "claims":[{"id":"identity","kind":"fact","statement":"Fixture Model v1 released","model_version":"v1","review_status":"verified",
                  "placements":[{"target":"B","block_id":"sheetBlock","range":"A2:C2"}],
                  "sources":[{"url":"https://fixture.example/release","retrieved_at":utc_now(),"locator":"release paragraph",
                              "local_path":"html/source.txt","content_sha256":file_digest(root/"html/source.txt")}]}],
       "claim_coverage":{"identity":{"status":"covered","claim_ids":["identity"]}},"verification":{}}
    for category in ("availability","pricing","capabilities","benchmarks","release","community"):
        m["claim_coverage"][category]={"status":"not_public","reason":"synthetic fixture","checked_urls":["https://fixture.example/release"]}
    invalidate(m,"fixture initialized")
    return m


class FakeHelper:
    def __init__(self):
        self.revision=1
        self.blocks=[{"block_id":"parentDoc","block_type":1,"children":["sheetBlock"]},
                     {"block_id":"sheetBlock","block_type":30,"parent_id":"parentDoc","sheet":{"token":"spreadsheet_sheet1"}}]
        self.values=[["Model","Price","Total"],["Fixture v1",2,4],[None,None,None],[None,None,None]]
        self.formulas=[[None,None,None],[None,None,"=B2*2"],[None,None,None],[None,None,None]]
        self.read_calls=0
        self.change_after=None
        self.media={}
    def api(self,method,path):
        assert method=="GET"
        if "get_node" in path:
            data={"node":{"node_token":"parentWiki","obj_token":"parentDoc","parent_node_token":"rootWiki"}}
        else:
            data={"document":{"document_id":"parentDoc","title":"Fixture parent","revision_id":self.revision}}
        return None,{"code":0,"data":data}
    def _all_blocks(self,token):
        return copy.deepcopy(self.blocks)
    def sheet_metadata(self,token,sheet):
        return {"row_count":len(self.values),"column_count":3,"sheet_id":sheet}
    def read_sheet_range(self,token,sheet,a1):
        from validate_tables import range_shape
        r1,r2,c1,c2=range_shape(a1)
        self.read_calls+=1
        if self.change_after and self.read_calls>=self.change_after:
            self.values[1][1]=99
        return {"range":a1,"row_indices":list(range(r1,r2+1)),"col_indices":[chr(64+c) for c in range(c1,c2+1)],
                "values":copy.deepcopy([row[c1-1:c2] for row in self.values[r1-1:r2]]),
                "formulas":copy.deepcopy([row[c1-1:c2] for row in self.formulas[r1-1:r2]])}
    def download_media(self,token):
        return self.media[token]


def parent_entry():
    import validate_vendor_section as vv
    blocks={}
    def add(bid,typ,parent=None,children=None,text=None,els=None):
        b={"block_id":bid,"block_type":typ}
        if parent is not None:b["parent_id"]=parent
        if children is not None:b["children"]=children
        if text is not None or els is not None:b[vv.TEXT_KEYS[typ]]={"elements":els if els is not None else [{"text_run":{"content":text}}]}
        blocks[bid]=b
    add("h",5,"root",text="【2026/09/11】Fixture Model: audit")
    add("detail",2,"root",els=[{"text_run":{"content":"详细追踪："}},{"mention_doc":{"title":"Child","token":"childWiki","url":"https://fixture.feishu.cn/wiki/childWiki"}}])
    add("main",24,"root",["left","right"]);add("left",25,"main",["cap","case"]);add("right",25,"main",["params","bench","image"])
    add("cap",2,"left",text="核心能力：fixture");add("case",2,"left",text="展示的 Case：fixture")
    add("params",2,"right",text="关键参数：fixture");add("bench",2,"right",text="测评：fixture caption")
    add("image",27,"right");blocks["image"]["image"]={"width":600,"height":300,"token":"fixtureMedia"}
    add("socialLabel",2,"root",text="宣发/社媒");add("social",24,"root",["socialLeft","socialRight"])
    add("socialLeft",25,"social",["analysis","urls"]);add("socialRight",25,"social",[])
    add("analysis",2,"socialLeft",text="传播分析 fixture")
    add("urls",2,"socialLeft",els=[{"text_run":{"content":"网页"}},*[{"text_run":{"content":url,"text_element_style":{"link":{"url":url}}}} for url in ["https://fixture.example/release","https://fixture.example/docs"]]])
    return ["h","detail","main","socialLabel","social"],blocks
