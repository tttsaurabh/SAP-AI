import os, sys, glob
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from app.core.config import settings
from app.services.parser import DocumentParser
from app.services.chunker import DocumentChunker
pub = r"c:/Users/tttsa/Desktop/SAP AI/public"
total_children=0; total_parents=0
for f in sorted(glob.glob(os.path.join(pub,'*.pdf'))):
    name=os.path.basename(f)
    try:
        pages=DocumentParser.parse_file(f,name)
        parents=DocumentChunker.chunk_document_hierarchical(pages, parent_size=settings.PARENT_CHUNK_SIZE_TOKENS, child_size=settings.CHILD_CHUNK_SIZE_TOKENS, child_overlap=settings.CHILD_CHUNK_OVERLAP_TOKENS)
        ch=sum(len(p.get('children',[])) for p in parents)
        total_children+=ch; total_parents+=len(parents)
        print(f"{name[:45]:45s} pages={len(pages):4d} parents={len(parents):4d} children={ch:4d}", flush=True)
    except Exception as e:
        print(f"{name[:45]:45s} PARSE-FAIL: {repr(e)[:80]}", flush=True)
print(f"\nTOTAL parents={total_parents} children(to_embed)={total_children}")
print(f"Free-tier 100 embeds/min -> ~{total_children/100:.0f} min throttled")
