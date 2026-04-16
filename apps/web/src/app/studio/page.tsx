import { StudioForm } from "@/components/studio-form";

export default function StudioPage() {
  return (
    <div className="mx-auto max-w-7xl space-y-4 p-8">
      <header>
        <h1 className="text-3xl font-semibold tracking-tight">스튜디오</h1>
        <p className="text-sm text-muted-foreground">
          텍스트·화자·파라미터를 선택해 음성을 생성합니다.
        </p>
      </header>
      <StudioForm />
    </div>
  );
}
