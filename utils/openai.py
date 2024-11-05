from openai import OpenAI


## api Key를 받는다
# Prompt는 입력으로 받은 문장들을 하나의 문장으로


def request_to_openai(api_key, content):
    prompt = f"""
        자막을 넣기 위해 대본을 문장단위로 나누고싶어.
        다음 텍스트를 문장 단위로 나눠줘. 이 텍스트는 한글로 작성되어있어. 각 문장은 한 줄이 아닌 다음 줄로 구분되도록 해줘.
        조건은 다음과 같아:

        1. 입력으로 들어온 텍스트는 변형 없이 그대로 유지해야 한다. 하지만 문장을 나누거나 합치는 것은 괜찮아
        2. 출력 결과는 문장 번호 없이 문장만 출력해야 한다.
        3. 문장의 의미가 자연스럽게 이어지도록 하기 위해 필요하면 이전 또는 다음 문장과 합쳐줘
        4. 각 문장은 최대 40자 이내로 유지해줘. 만약 40자가 넘어가면 한국어가 자연스럽게 문장을 다음 줄로 넘겨줘. 말이 잘리지 않도록 해줘
        5. 이 글을 요약하거나 해석하지 말고, 문장을 나누거나 합친 그대로의 결과를 보여줘.
        6. 명심해줘. 입력으로 들어온 텍스트들은 변형이 없어야해 요약이나 의견도 추가하지 말아줘.
        얘를 들면 문장 사이에 특수기호를 넣는다던가 맞춤법을 수정한다던가 매끄러운 문장으로 만든다던가 하는 변형은 하지 말아줘.

        예시는 아래와 같아:
        - 변형 전
            네 창신동에 박선생님, 아, 요컨대요, 현재 논란의 중심은 바로 소득 상위계층의 세금을
            덜 걷겠다는 부분인데요, 어떠세요? 생업에 종사하시면서 직접 피부로 와닿는 부분도 
            있으실 텐데요

        - 변형 후
            네 창신동에 박선생님, 아, 요컨대요, 현재 논란의 중심은 바로
            소득 상위계층의 세금을 덜 걷겠다는 부분인데요, 
            어떠세요? 생업에 종사하시면서 직접 피부로 와닿는 부분도 있으실 텐데요
        
        텍스트: {content}
        """
    client = OpenAI(api_key=api_key)

    response = client.chat.completions.create(
        messages=[
            {
                "role": "system",
                "content": "You are a helpful assistant that can split text into sentences.",
            },
            {
                "role": "user",
                "content": prompt,
            },
        ],
        model="gpt-4o",
        temperature=0.5,
    )

    return response.choices[0].message.content
