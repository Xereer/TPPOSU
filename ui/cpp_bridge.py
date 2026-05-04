from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import subprocess
from typing import Callable, List, Optional

from sqlmodel import Session

from ui.database import Experiments, Measurements, engine


FRAME_PREFIX = "FRAME\t"
END_TIME_PREFIX = "END_TIME_MSK\t"


@dataclass
class MeasurementRunResult:
    rows: List[list]
    end_time: datetime


def get_measurement_executable() -> Path:
    root = Path(__file__).resolve().parent.parent
    candidates = [
        root / "core_cpp" / "Practice.exe",
        root / "core_cpp" / "Practice",
        root / "core_cpp" / "Release" / "Practice.exe",
        root / "core_cpp" / "Debug" / "Practice.exe",
    ]

    for candidate in candidates:
        if candidate.exists():
            return candidate

    raise FileNotFoundError(
        "Не найден исполняемый файл core_cpp/Practice(.exe). "
        "Сначала соберите C++-часть."
    )


def run_measurement_pipeline(
    frame_count: int,
    progress_callback: Optional[Callable[[int, int], None]] = None,
    stability_reads: int = 1,
    stability_tolerance: float = 0.0,
    channel6_reads: int = 10,
) -> MeasurementRunResult:
    executable = get_measurement_executable()
    command = [
        str(executable),
        str(frame_count),
        str(stability_reads),
        str(stability_tolerance),
        str(channel6_reads),
    ]

    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
    )

    rows: List[list] = []
    end_time: Optional[datetime] = None

    assert process.stdout is not None
    for raw_line in process.stdout:
        line = raw_line.strip()
        if not line:
            continue

        if line.startswith(FRAME_PREFIX):
            parts = line.split("\t")
            if len(parts) != 12:
                raise RuntimeError(f"Некорректный формат строки измерения: {line}")

            row = [
                int(parts[1]),
                float(parts[2]),
                float(parts[3]),
                float(parts[4]),
                float(parts[5]),
                int(parts[6]),
                float(parts[7]),
                float(parts[8]),
                float(parts[9]),
                float(parts[10]),
                float(parts[11]),
            ]
            rows.append(row)

            if progress_callback is not None:
                progress_callback(len(rows), frame_count)
            continue

        if line.startswith(END_TIME_PREFIX):
            end_time_raw = line.split("\t", 1)[1]
            end_time = datetime.strptime(end_time_raw, "%Y-%m-%d %H:%M:%S")
            continue

        raise RuntimeError(f"Неожиданная строка от core_cpp: {line}")

    stderr_output = ""
    if process.stderr is not None:
        stderr_output = process.stderr.read().strip()

    return_code = process.wait()
    if return_code != 0:
        raise RuntimeError(stderr_output or f"core_cpp завершился с кодом {return_code}")

    if end_time is None:
        raise RuntimeError("core_cpp не вернул конечное время эксперимента")

    return MeasurementRunResult(rows=rows, end_time=end_time)


def save_measurement_run(experiment_id: int, result: MeasurementRunResult) -> None:
    with Session(engine) as session:
        objects = []

        for row in result.rows:
            objects.append(
                Measurements(
                    experiment_id=experiment_id,
                    number=row[0],
                    channel_1=row[1],
                    channel_2=row[2],
                    channel_3=row[3],
                    channel_4=row[4],
                    channel_5=row[5],
                    channel_6_avg=row[6],
                    channel_6_disp=row[7],
                    channel_19=row[8],
                    channel_49=row[9],
                    channel_69_func=row[10],
                )
            )

        session.add_all(objects)

        experiment = session.get(Experiments, experiment_id)
        if experiment is None:
            raise RuntimeError(f"Эксперимент с ID={experiment_id} не найден")

        experiment.end_time = result.end_time
        session.add(experiment)
        session.commit()
