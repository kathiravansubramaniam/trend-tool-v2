interface Source {
  gcs_name: string;
  name: string;
  industry: string;
  topics: string[];
  url?: string | null;
}

export default function SourceCard({ source }: { source: Source }) {
  const inner = (
    <div className="rounded-lg border border-[#2e2e2e] bg-[#1a1a1a] px-3 py-2 text-sm transition-colors hover:border-[#6366f1]">
      <p className="font-medium text-[#e8e8e8] leading-snug truncate" title={source.name}>
        {source.name}
      </p>
      {source.industry && (
        <p className="text-[#6366f1] text-xs mt-0.5">{source.industry}</p>
      )}
      {source.topics.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {source.topics.slice(0, 3).map((t) => (
            <span key={t} className="bg-[#242424] text-[#888] text-xs px-1.5 py-0.5 rounded">
              {t}
            </span>
          ))}
        </div>
      )}
    </div>
  );

  if (source.url) {
    return (
      <a href={source.url} target="_blank" rel="noopener noreferrer" className="block">
        {inner}
      </a>
    );
  }

  return inner;
}
