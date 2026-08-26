import re
from dataclasses import dataclass


@dataclass
class Chunk:
    index: int
    content: str
    section_path: str
    token_count: int = 0


def chunk_markdown(content: str, max_size: int = 800, overlap: int = 100) -> list[Chunk]:
    if not content or not content.strip():
        return []

    heading_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)
    paragraphs = re.split(r'\n\s*\n', content.strip())

    sections: list[tuple[str, str]] = []
    current_path: list[str] = []
    buffer: list[str] = []

    for para in paragraphs:
        heading_match = heading_pattern.match(para.strip())
        if heading_match:
            level = len(heading_match.group(1))
            heading_text = heading_match.group(2).strip()
            current_path = current_path[: level - 1] + [heading_text]
            if buffer:
                sections.append((" > ".join(current_path[:-1]), "\n\n".join(buffer).strip()))
                buffer = []
            buffer.append(para)
        else:
            buffer.append(para)

    if buffer:
        sections.append((" > ".join(current_path), "\n\n".join(buffer).strip()))

    chunks: list[Chunk] = []
    chunk_index = 0

    for section_path, section_content in sections:
        if not section_content:
            continue

        if len(section_content) <= max_size:
            chunks.append(Chunk(
                index=chunk_index,
                content=section_content,
                section_path=section_path,
                token_count=len(section_content),
            ))
            chunk_index += 1
            continue

        sentences = re.split(r'(?<=[。！？.!?])\s+', section_content)
        current_chunk_text = ""

        for sentence in sentences:
            if len(current_chunk_text) + len(sentence) + 1 <= max_size:
                current_chunk_text += (" " if current_chunk_text else "") + sentence
            else:
                if current_chunk_text:
                    chunks.append(Chunk(
                        index=chunk_index,
                        content=current_chunk_text.strip(),
                        section_path=section_path,
                        token_count=len(current_chunk_text.strip()),
                    ))
                    chunk_index += 1

                if len(sentence) > max_size:
                    for i in range(0, len(sentence), max_size - overlap):
                        piece = sentence[i : i + max_size]
                        chunks.append(Chunk(
                            index=chunk_index,
                            content=piece.strip(),
                            section_path=section_path,
                            token_count=len(piece.strip()),
                        ))
                        chunk_index += 1
                    current_chunk_text = ""
                else:
                    current_chunk_text = sentence

        if current_chunk_text:
            chunks.append(Chunk(
                index=chunk_index,
                content=current_chunk_text.strip(),
                section_path=section_path,
                token_count=len(current_chunk_text.strip()),
            ))
            chunk_index += 1

    return chunks
