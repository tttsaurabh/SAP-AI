import re
from typing import List, Dict, Any
from loguru import logger

class DocumentChunker:
    @staticmethod
    def chunk_document(pages: List[Dict[str, Any]], chunk_size: int = 1200, chunk_overlap: int = 200) -> List[Dict[str, Any]]:
        """
        Segments a list of pages into structured overlapping chunks.
        Appends page number and active headings to help context retrieval.
        """
        chunks = []
        chunk_idx = 0
        current_header = "General Information"
        
        for p in pages:
            page_num = p.get("page", 1)
            page_text = p.get("text", "")
            page_metadata = p.get("metadata", {})
            
            # If the page has headings metadata, grab the first one as initial header
            page_headings = page_metadata.get("headings", [])
            if page_headings:
                current_header = page_headings[0]
                
            # If the page is empty, skip
            if not page_text.strip():
                continue
                
            # Split page text into lines/paragraphs
            paragraphs = re.split(r'\n{2,}', page_text)
            
            current_chunk_text = ""
            for para in paragraphs:
                para = para.strip()
                if not para:
                    continue
                
                # Check if paragraph contains heading tags
                # (e.g., "# 1. SAP MDG Architecture" or "WORKFLOW STEPS:")
                heading_match = re.match(r'^(?:#+\s*|CHAPTER\s+\d+\s*:\s*|SECTION\s+\d+\s*:\s*)([^\n]{3,100})', para, re.IGNORECASE)
                if heading_match:
                    current_header = heading_match.group(1).strip()
                
                # If paragraph fits into current chunk, append it
                if len(current_chunk_text) + len(para) < chunk_size:
                    if current_chunk_text:
                        current_chunk_text += "\n\n" + para
                    else:
                        current_chunk_text = para
                else:
                    # Flush current chunk
                    if current_chunk_text:
                        chunks.append({
                            "chunk_index": chunk_idx,
                            "text": current_chunk_text,
                            "page_number": page_num,
                            "section_header": current_header,
                            "chunk_metadata": {
                                "source_page": page_num,
                                "section": current_header
                            }
                        })
                        chunk_idx += 1
                    
                    # Restart chunk with overlap
                    # Simple overlap: grab trailing characters or keep paragraph if small
                    overlap_text = current_chunk_text[-chunk_overlap:] if len(current_chunk_text) > chunk_overlap else ""
                    if overlap_text:
                        # Clean up overlap to start on a full sentence if possible
                        sentence_boundary = overlap_text.find(". ")
                        if sentence_boundary != -1 and sentence_boundary < len(overlap_text) - 10:
                            overlap_text = overlap_text[sentence_boundary+2:]
                    
                    current_chunk_text = overlap_text + "\n\n" + para if overlap_text else para
            
            # Flush final chunk of the page
            if current_chunk_text:
                chunks.append({
                    "chunk_index": chunk_idx,
                    "text": current_chunk_text,
                    "page_number": page_num,
                    "section_header": current_header,
                    "chunk_metadata": {
                        "source_page": page_num,
                        "section": current_header
                    }
                })
                chunk_idx += 1
                
        logger.info(f"Generated {len(chunks)} chunks from {len(pages)} pages")
        return chunks
