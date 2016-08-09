import subprocess


def run_flow(text, job_id, count, token, secret):
    subprocess.run([
        'python',
        '-m',
        'luigi',
        '--module',
        'summarize',
        'RunFlow',
        '--term',
        text,
        '--jobid',
        str(job_id),
        '--count',
        str(count),
        '--token',
        str(token),
        '--secret',
        str(secret)
        ])
