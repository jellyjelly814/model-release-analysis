import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch
from tests.fixtures import manifest,FakeHelper
from sync_common import atomic_json
import validate_child_document as child


class ChildTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.m=manifest(self.temp.name,["C"]);self.helper=FakeHelper();blocks=[];self.by_id={}
        def add(bid,typ,parent="childDoc",children=None,text=None,urls=()):
            b={"block_id":bid,"block_type":typ,"parent_id":parent}
            if children is not None:b["children"]=children
            if text is not None:b[child.TEXT_KEYS[typ]]={"elements":[{"text_run":{"content":text}},*[{"text_run":{"content":u,"text_element_style":{"link":{"url":u}}}} for u in urls]]}
            blocks.append(b);self.by_id[bid]=b
        roots=["callout","wall","basic","features","f1","f2","benchmark","benchgrid","release","table","voices","socialgrid","demo","takeaway","return"]
        add("childDoc",1,None,roots);add("callout",19,children=["judgment","position","sources"])
        add("judgment",2,"callout",text="Fixture judgment");add("position",2,"callout",text="Fixture positioning")
        add("sources",2,"callout",text="Sources",urls=["https://fixture.example/release","https://fixture.example/docs"])
        add("wall",24,children=["w1","w2","w3","w4"])
        for n in range(1,5):add(f"w{n}",25,"wall",[f"img{n}"])
        for bid,text in [("basic","基本信息"),("features","模型特点 + 展示 Case"),("benchmark","Benchmark"),("release","发布过程"),("demo","社区 Demo"),("takeaway","MiniMax 可以借鉴的")]:add(bid,3,text=text)
        add("f1",4,text="Coding capability");add("f2",4,text="Vision capability");add("voices",4,text="发布过程与社区声势")
        add("benchgrid",24,children=["benchleft","benchright"]);add("benchleft",25,"benchgrid",["benchtext"]);add("benchright",25,"benchgrid",["img5"])
        add("benchtext",2,"benchleft",text="Fixture benchmark conditions")
        add("table",31,children=[])
        add("socialgrid",24,children=["s1","s2","s3"])
        for n in range(1,4):add(f"s{n}",25,"socialgrid",[f"socialtext{n}"]);add(f"socialtext{n}",2,f"s{n}",text="Fixture viewpoint")
        add("return",2,text="返回汇总页",urls=["https://fixture.feishu.cn/wiki/parentWiki"])
        self.m["screenshots"]=[]
        for n in range(1,6):
            bid=f"img{n}";add(bid,27,f"w{n}" if n<5 else "benchright")
            self.by_id[bid]["image"]={"width":800,"height":500,"token":bid}
            self.helper.media[bid]=f"synthetic image {n}".encode()
            self.m["screenshots"].append({"id":bid,"model_entry":self.m["parent_section"]["model_entry"],"child_image_block":bid,
                                         "content_sha256":hashlib.sha256(self.helper.media[bid]).hexdigest(),"source_original":f"https://fixture.example/image{n}",
                                         "source_class":["official_page","official_social","independent_benchmark","official_page","official_page"][n-1]})
        self.helper.blocks=blocks
        def api(method,path):
            if "get_node" in path:data={"node":{"node_token":"childWiki","obj_token":"childDoc","parent_node_token":"parentWiki"}}
            else:data={"document":{"title":self.m["child_wiki_doc"]["title"],"revision_id":self.helper.revision}}
            return None,{"code":0,"data":data}
        self.helper.api=api
    def run_child(self):
        path=Path(self.temp.name)/"manifest.json";atomic_json(path,self.m)
        argv=["child","--doc","childWiki","--parent-node","parentWiki","--manifest",str(path),"--helper","fixture"]
        out=io.StringIO()
        with patch.object(child,"load_helper",return_value=self.helper),patch("sys.argv",argv),redirect_stdout(out):
            with self.assertRaises(SystemExit):child.main()
        return json.loads(out.getvalue())
    def test_valid_template_and_image_bindings_pass(self):
        result=self.run_child();self.assertEqual(result["status"],"pass",result)
    def test_missing_benchmark_image_binding_fails(self):
        self.m["screenshots"].pop();self.assertEqual(self.run_child()["status"],"fail")
    def test_crop_of_same_original_cannot_fill_two_opening_slots(self):
        self.m["screenshots"][1]["source_original"]=self.m["screenshots"][0]["source_original"]
        self.assertEqual(self.run_child()["status"],"fail")
    def test_wrong_return_link_with_parent_token_in_query_fails(self):
        self.by_id["return"]["text"]["elements"][1]["text_run"]["text_element_style"]["link"]["url"]="https://fixture.feishu.cn/wiki/wrong?parentWiki"
        self.assertEqual(self.run_child()["status"],"fail")
    def test_image_hash_mismatch_fails(self):
        self.helper.media["img5"]=b"wrong image";self.assertEqual(self.run_child()["status"],"fail")
    def test_internal_execution_text_fails(self):
        self.by_id["benchtext"]["text"]["elements"][0]["text_run"]["content"]="规范化摘要"
        self.assertEqual(self.run_child()["status"],"fail")
